"""Session B entry point on Modal: SGLang (Gemma 4 26B-A4B FP8, judge server, no MTP) and the engine in one container.

  export MODAL_TOKEN_ID=$modal MODAL_TOKEN_SECRET=$modal_secret
  modal run --detach modal_engine.py --stage s6 --jobs '[{"config":"N1","dataset":"musique","split":"dev"}]'
  modal volume get sag2poc-b-results /s6 out/

SGLang image, launch flags and the L40S fused-MoE Triton config follow jevlike's modal_sglang.py.
The weights volume (gb10-decide-hf) is mounted read-only.
"""
import json
import os
import subprocess
import time
import urllib.request

import modal

MODEL_REPO, MODEL_REV = "RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic", "ed35d7abe5d9"
GPU = os.environ.get("SAG2POC_GPU", "L40S")
GPU_USD_PER_H = 1.95

app = modal.App("sag2poc-b-engine")
weights = modal.Volume.from_name("gb10-decide-hf").read_only()
results = modal.Volume.from_name("sag2poc-b-results", create_if_missing=True)

image = (
    modal.Image.from_registry("lmsysorg/sglang:gemma4-mtp", add_python=None)
    .entrypoint([])
    .pip_install("jieba==0.42.1", "opencc-python-reimplemented==0.1.7", "snowballstemmer==3.1.1", "requests")
    .run_commands(
        "python3 - <<'PY'\n"
        "import json, os\n"
        "dirs=['/sgl-workspace/sglang/python/sglang/srt/layers/moe/fused_moe_triton/configs/triton_3_5_1',"
        "      '/sgl-workspace/sglang/python/sglang/srt/layers/moe/moe_runner/triton_utils/configs/triton_3_6_0']\n"
        "small={'BLOCK_SIZE_M':16,'BLOCK_SIZE_N':64,'BLOCK_SIZE_K':128,'GROUP_SIZE_M':1,'num_warps':4,'num_stages':3}\n"
        "big={'BLOCK_SIZE_M':64,'BLOCK_SIZE_N':64,'BLOCK_SIZE_K':128,'GROUP_SIZE_M':8,'num_warps':4,'num_stages':3}\n"
        "cfg={str(m):(small if m<=32 else big) for m in [1,2,4,8,16,24,32,48,64,96,128,256,512,1024,1536,2048,3072,4096]}\n"
        "for d in dirs:\n"
        "  os.makedirs(d, exist_ok=True)\n"
        "  for n in ['E=128,N=704,device_name=NVIDIA_L40S,dtype=fp8_w8a8,per_channel_quant=True.json','E=128,N=704,device_name=NVIDIA_L40S,dtype=fp8_w8a8,per_channel_quant=True_down.json']:\n"
        "    json.dump(cfg, open(os.path.join(d,n),'w'), indent=1)\n"
        "print('wrote moe configs')\n"
        "PY"
    )
    .add_local_dir("engine", remote_path="/root/engine")
    .add_local_dir("evalkit", remote_path="/root/evalkit")
    .add_local_dir("data", remote_path="/root/data")
    .add_local_file("results/thresholds.lock.json", remote_path="/root/results/thresholds.lock.json")
)


def start_server(port=30000, ctx=16384, max_running=64, extra=()):
    cmd = ["python3", "-m", "sglang.launch_server", "--model-path", f"/hf/{MODEL_REPO}", "--context-length", str(ctx),
           "--max-running-requests", str(max_running), "--mem-fraction-static", "0.8", "--host", "127.0.0.1", "--port", str(port),
           "--log-level", "warning", *extra]
    print("starting:", " ".join(cmd), flush=True)
    t0 = time.time()
    proc = subprocess.Popen(cmd)
    for _ in range(1800):
        if proc.poll() is not None:
            raise RuntimeError(f"sglang exited early {proc.returncode}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            print(f"sglang healthy after {time.time() - t0:.1f}s", flush=True)
            return proc, time.time() - t0
        except Exception:  # noqa: BLE001
            time.sleep(1)
    proc.terminate()
    raise RuntimeError("sglang not healthy")


@app.function(image=image, gpu=GPU, volumes={"/hf": weights, "/results": results}, timeout=60 * 60 * 4)
def run(stage: str, jobs: str, run_id: str = ""):
    """jobs: JSON list of {"config", "dataset", "split", "lang"?, "tag"?, "limit"?, "tau"?, "out_mode"?, "data_root"?, "doc_level"?}"""
    import sys

    sys.path.insert(0, "/root")
    t_container = time.time()
    from engine.analyze import Analyzer
    from engine.decide import LLMDecider, SGLangBackend
    from engine.pipeline import Engine
    from engine.run import get_index, load_lock, make_config, run_split
    from evalkit import aggregate, load_questions, load_split, score_run

    jobs = json.loads(jobs)
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    lock = load_lock("/root/results/thresholds.lock.json")
    need_gpu = any(make_config(j["config"], lock).judge for j in jobs)
    proc, t_start = (start_server() if need_gpu else (None, 0.0))
    smi = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    env = {"run_id": run_id, "gpu": smi, "server_start_s": round(t_start, 1), "model": MODEL_REPO, "rev": MODEL_REV, "jobs": jobs}
    out_root = f"/results/{stage}"
    os.makedirs(out_root, exist_ok=True)
    report = []
    try:
        backend = SGLangBackend("http://127.0.0.1:30000", f"/hf/{MODEL_REPO}/tokenizer.json", cache_dir="/results/cache", run_id=run_id) if need_gpu else None
        if backend:
            print(f"judge cache: {backend.loaded} entries", flush=True)

        def flush():
            if backend:
                backend.flush()
            results.commit()

        analyzers, indexes = {}, {}
        for j in jobs:
            t_job = time.time()
            ds, split, lang = j["dataset"], j.get("split", "dev"), j.get("lang", "en")
            data_root = j.get("data_root", "/root/data")
            zh_key = j.get("zh_key", lock.get("zh_key", "tw2sp"))
            an = analyzers.setdefault(zh_key, Analyzer(zh_key=zh_key))
            ikey = (data_root, ds, zh_key)
            if ikey not in indexes:
                indexes[ikey] = get_index(ds, data_root, "/tmp/idx" + data_root.replace("/", "_"), an, lock.get("weights"), tag=f"-{zh_key}",
                                          doc_field=j.get("doc_field"))
            ix = indexes[ikey]
            cfg = make_config(j["config"], lock, tau=j.get("tau"), out_mode=j.get("out_mode"), rounds=j.get("rounds"), beta=j.get("beta"))
            questions = load_questions(ds, data_root)
            qids = load_split(ds, split, data_root)
            if j.get("limit"):
                qids = qids[: int(j["limit"])]
            eng = Engine(ix, LLMDecider(backend, lang) if cfg.judge else None, doc_level=bool(j.get("doc_level")))
            tag = j.get("tag") or f"{ds}-{split}-{j['config']}"
            out_dir = f"{out_root}/{tag}"
            summ = run_split(eng, cfg, questions, qids, out_dir, workers=int(j.get("workers", 16)), flush=flush)
            run_rows = {json.loads(l)["qid"]: json.loads(l)["retrieved"] for l in open(f"{out_dir}/run.jsonl")}
            agg = aggregate(score_run(questions, run_rows, qids))
            row = {"tag": tag, "job_s": round(time.time() - t_job, 1), "calls_median": summ["calls_median"], "fresh_calls": summ["fresh_calls"],
                   "fresh_tokens": summ["fresh_tokens"], "min_mass": summ["min_option_mass"], **{k: round(v, 2) for k, v in agg.items()}}
            print(json.dumps(row), flush=True)
            report.append(row)
            env["report"] = report
            env["container_s"] = round(time.time() - t_container, 1)
            env["est_usd"] = round(env["container_s"] * GPU_USD_PER_H / 3600, 3)
            json.dump(env, open(f"{out_root}/_run_{run_id}.json", "w"), indent=1)
            flush()
    finally:
        if proc:
            proc.terminate()
        env["container_s"] = round(time.time() - t_container, 1)
        env["est_usd"] = round(env["container_s"] * GPU_USD_PER_H / 3600, 3)
        env["done"] = True
        json.dump(env, open(f"{out_root}/_run_{run_id}.json", "w"), indent=1)
        results.commit()
    return env


@app.local_entrypoint()
def main(stage: str = "smoke", jobs: str = "[]", run_id: str = ""):
    env = run.remote(stage, jobs, run_id)
    print(json.dumps(env, indent=1, ensure_ascii=False)[:8000])
