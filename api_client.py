# -*- coding: utf-8 -*-
"""网络调用：流式输出、Esc 停止检查和连续失败熔断。"""
import sys, json, time, copy, queue, threading, requests
from config import API, KEY, MODEL, THRESH, COOL
from file_tools import TOOLS
from terminal import poll_control

# 网络状态由本模块维护，聊天模块通过 api.STOP 读取停止标志。
FAILS=0; OPEN=False; UNTIL=0.0; STOP=False; EXIT=False

def check_control():
    global STOP,EXIT
    command=poll_control()
    if command:
        STOP=True; EXIT=command=="/exit"
        print("\n[Exiting]" if EXIT else "\n[Stopped]",flush=True)
    return STOP

# 网络在后台读取；主线程每 0.05 秒检查命令，连接等待时也能返回输入提示。
def network_lines(msgs):
    packets=queue.Queue(maxsize=16); cancelled=threading.Event()
    payload={"model":MODEL,"messages":copy.deepcopy(msgs),"tools":TOOLS,"stream":True}
    headers={"Authorization":"Bearer "+KEY}
    def put(kind,value=None):
        while not cancelled.is_set():
            try: packets.put((kind,value),timeout=0.05); return
            except queue.Full: pass
    def read():
        r=None
        try:
            r=requests.post(API,headers=headers,json=payload,timeout=(5,60),stream=True)
            r.raise_for_status()
            if cancelled.is_set(): return
            for line in r.iter_lines(chunk_size=1):
                if cancelled.is_set(): break
                put("line",line)
        except Exception as e: put("error",e)
        finally:
            if r is not None:
                try: r.close()
                except Exception: pass
            put("done")
    threading.Thread(target=read,daemon=True).start()
    try:
        while not check_control():
            try: kind,value=packets.get(timeout=0.05)
            except queue.Empty: continue
            if kind=="error": raise value
            if kind=="done": return
            yield value
    finally:
        # 取消后的响应不再显示或执行；后台读取结束后关闭连接。
        cancelled.set()

def stream(msgs):
    global FAILS,OPEN,UNTIL,STOP
    STOP=False
    if OPEN:
        if time.time()<UNTIL: raise RuntimeError("Circuit breaker open")
        OPEN=False; FAILS=0
    lines=network_lines(msgs); content=""; buf={}
    try:
        for line in lines:
            if not line or not line.startswith(b"data:"): continue
            pl=line[5:].strip()
            if pl==b"[DONE]": break
            d=json.loads(pl)["choices"][0]["delta"]
            if d.get("content"):
                content+=d["content"]; sys.stdout.write(d["content"]); sys.stdout.flush()
            # 同一个工具调用的参数可能分多段到达，按索引拼接。
            for tc in d.get("tool_calls") or []:
                i=tc.get("index",0); s=buf.setdefault(i,{"id":"","name":"","args":""})
                if tc.get("id"): s["id"]=tc["id"]
                fn=tc.get("function") or {}
                if fn.get("name"): s["name"]=fn["name"]
                if fn.get("arguments"): s["args"]+=fn["arguments"]
        FAILS=0
    except Exception:
        FAILS+=1
        if FAILS>=THRESH and not OPEN:
            OPEN=True; UNTIL=time.time()+COOL
            print("\n[Circuit open] %d failures; wait %d seconds"%(FAILS,COOL))
        raise
    finally:
        lines.close()
    # 只将能解析为 JSON 的工具参数交给聊天循环。
    tcs=[]
    for i in sorted(buf):
        s=buf[i]
        if not s["id"] or not s["name"]: continue
        try: json.loads(s["args"] or "{}")
        except: continue
        tcs.append({"id":s["id"],"type":"function","function":{"name":s["name"],"arguments":s["args"] or "{}"}})
    m={"role":"assistant","content":content or None}
    if tcs: m["tool_calls"]=tcs
    msgs.append(m)
    return content,tcs
