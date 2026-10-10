# -*- coding: utf-8 -*-
"""聊天与工具循环：接收任务、执行模型请求的动作，再将结果交回模型。"""
import json
import api_client as api
from config import KEY, ROOT, MAX_CHARS, MAX_WRITES
from file_tools import WT, run
from terminal import read_prompt, show_action, show_result

WRITES=0

def main():
    global WRITES
    if not KEY: print("Set KEY before running"); return
    # 当前会话保留完整历史，不按消息条数裁剪。
    msgs=[{"role":"system","content":"You are a file assistant. Workspace: "+ROOT+". Handle files carefully. Reply in the user's language."}]
    print("Workspace:",ROOT)
    print("Commands: /quit stops the task; /exit exits. Esc also stops.")
    while True:
        try: u=read_prompt().strip()
        except (EOFError,KeyboardInterrupt): break
        if not u: continue
        if u.lower() in("/exit","exit","quit"): break
        if u.lower()=="/quit":
            print("[No task is running]"); continue
        if u.startswith("/"):
            print("Unknown command. Use /quit or /exit."); continue
        msgs.append({"role":"user","content":u})
        # 记录本轮追加位置；中断时丢弃后续消息，不撤销文件修改。
        snap=len(msgs); WRITES=0; api.STOP=False; action_no=0
        try:
            # 持续调用模型，直到没有工具调用或用户主动中断。
            while True:
                if api.check_control(): break
                print("\nAssistant> ",end="",flush=True)
                _,tcs=api.stream(msgs); print()
                if api.STOP or not tcs: break
                for tc in tcs:
                    if api.check_control(): break
                    n=tc["function"]["name"]
                    action_no+=1
                    try:
                        a=json.loads(tc["function"]["arguments"] or "{}")
                        if not isinstance(a,dict): raise ValueError("Expected an object")
                    except Exception as e:
                        res="Invalid arguments: %s"%e
                        show_action(action_no,n,{})
                        show_result(n,res)
                        msgs.append({"role":"tool","tool_call_id":tc["id"],"content":res}); continue
                    # 动作先显示，再执行；结果预览只用于终端。
                    show_action(action_no,n,a)
                    if n in WT:
                        if WRITES>=MAX_WRITES:
                            show_result(n,"Write limit reached")
                            msgs.append({"role":"tool","tool_call_id":tc["id"],"content":"Write limit reached"}); continue
                        WRITES+=1
                    try: res=run(n,a)
                    except Exception as e: res="Failed: %s"%e
                    res=str(res)
                    show_result(n,res)
                    # 完整文件正文交给模型，其他工具仍使用字符上限。
                    if n!="read_file" and len(res)>MAX_CHARS: res=res[:MAX_CHARS]+"...[truncated]"
                    # 用调用 ID 关联结果，供下一次模型请求使用。
                    msgs.append({"role":"tool","tool_call_id":tc["id"],"content":res})
                    if api.STOP: break
                if api.STOP: break
            if api.STOP:
                del msgs[snap:]; print("[Turn discarded]"); api.STOP=False
            if api.EXIT: break
        except KeyboardInterrupt:
            del msgs[snap:]; api.STOP=False; print("\n[Interrupted; turn discarded]")
        except Exception as e:
            del msgs[snap:]; api.STOP=False; print("\n[Error]",e)
    print("Bye")
