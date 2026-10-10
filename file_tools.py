# -*- coding: utf-8 -*-
"""文件工具：定义模型可用的工具，并执行工作区内的文件操作。"""
import os, shutil, fnmatch, stat
from config import ROOT

# 工具描述发送给模型，保持简短英文。
TOOLS=[{"type":"function","function":{"name":n,"description":d,"parameters":p}}
 for n,d,p in [
 ("search_text","Search literal, case-sensitive text recursively or in one file. Return path:line:text. path defaults to workspace, glob to *, encoding to utf-8.",{"type":"object","properties":{"query":{"type":"string"},"path":{"type":"string"},"glob":{"type":"string"},"encoding":{"type":"string"}},"required":["query"]}),
 ("find_files","Find files recursively by name, e.g. *.py or *main*. path defaults to workspace.",{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"]}),
 ("list_files","List files and folders. path defaults to workspace; list subfolders to locate files.",{"type":"object","properties":{"path":{"type":"string"}}}),
 ("read_file","Read the full file.",{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
 ("write_file","Write or overwrite a file.",{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}),
 ("append_file","Append text to a file.",{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}),
 ("replace_in_file","Replace an exact, unique text match.",{"type":"object","properties":{"path":{"type":"string"},"old":{"type":"string"},"new":{"type":"string"}},"required":["path","old","new"]}),
 ("delete_file","Delete a file or folder.",{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
]]
# 会修改文件的工具，计入单轮写操作次数。
WT=("write_file","append_file","replace_in_file","delete_file")

# 将路径解析为真实路径，限制访问范围为工作区。
def safe(p):
    r=os.path.realpath(ROOT); f=os.path.realpath(os.path.join(r,p))
    if f!=r and not f.startswith(r+os.sep): raise ValueError("Outside workspace: "+p)
    return f

# 共用文件遍历逻辑；跳过目录链接和 Windows Junction。
def iter_files(p):
    if os.path.isfile(p):
        yield p
        return
    for base,dirs,files in os.walk(p,followlinks=False):
        dirs[:] = [d for d in sorted(dirs)
                   if not (getattr(os.lstat(os.path.join(base,d)),"st_file_attributes",0)
                           & stat.FILE_ATTRIBUTE_REPARSE_POINT)]
        for name in sorted(files):
            yield os.path.join(base,name)

def run(n,a):
    if n=="search_text":
        p=safe(a.get("path",".")); query=a["query"]
        if not os.path.exists(p): return "Not found"
        if not query: return "Query must not be empty"
        pattern=a.get("glob","*").lower(); found=[]; skipped=0
        for candidate in iter_files(p):
            if not fnmatch.fnmatchcase(os.path.basename(candidate).lower(),pattern): continue
            try:
                target=safe(candidate)
                # 用文件头的零字节粗略识别二进制文件。
                with open(target,"rb") as f:
                    if b"\0" in f.read(1024): continue
                # 逐行搜索，返回文件路径、从 1 开始的行号和匹配内容。
                with open(target,encoding=a.get("encoding","utf-8"),errors="replace") as f:
                    for line_no,line in enumerate(f,1):
                        if query in line:
                            found.append("%s:%d: %s"%(os.path.relpath(candidate,ROOT),line_no,line.rstrip("\r\n")))
            except (OSError,ValueError): skipped+=1
        result="\n".join(found) or "No matches"
        return result+("\nSkipped unreadable files: %d"%skipped if skipped else "")
    if n=="find_files":
        p=safe(a.get("path",".")); pattern=a["pattern"].lower()
        if not os.path.isdir(p): return "Folder not found"
        found=[]
        for candidate in iter_files(p):
            if fnmatch.fnmatchcase(os.path.basename(candidate).lower(),pattern):
                found.append(os.path.relpath(candidate,ROOT))
        return "\n".join(sorted(found)) or "No matching files"
    if n=="list_files":
        p=safe(a.get("path","."))
        if not os.path.isdir(p): return "Folder not found"
        return "\n".join(("[DIR] " if os.path.isdir(os.path.join(p,f)) else "[FILE] ")+f
                         for f in sorted(os.listdir(p))) or "Empty folder"
    if n=="read_file":
        p=safe(a["path"])
        if not os.path.isfile(p): return "Not found"
        with open(p,encoding="utf-8",errors="replace") as f: s=f.read()
        return s
    # 覆盖与追加共用实现，只切换文件打开模式。
    if n in ("write_file","append_file"):
        p=safe(a["path"]); os.makedirs(os.path.dirname(p),exist_ok=True)
        with open(p,"w" if n=="write_file" else "a",encoding="utf-8") as f: f.write(a["content"])
        return "Written" if n=="write_file" else "Appended"
    if n=="replace_in_file":
        p=safe(a["path"]); t=open(p,encoding="utf-8").read(); c=t.count(a["old"])
        if c==0: return "Text not found"
        if c>1: return "Found %d matches; expected one"%c
        open(p,"w",encoding="utf-8").write(t.replace(a["old"],a["new"],1)); return "Replaced"
    if n=="delete_file":
        p=safe(a["path"])
        if not os.path.exists(p): return "Not found"
        os.remove(p) if os.path.isfile(p) else shutil.rmtree(p); return "Deleted"
    return "Unknown tool"
