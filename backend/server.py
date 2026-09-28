import json, os, re, sqlite3, time, urllib.parse, urllib.request, urllib.robotparser, mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from collections import deque, Counter

BASE_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB=os.path.join(BASE_DIR,"data","seo.db")
FRONTEND_DIR=os.path.join(BASE_DIR,"frontend")
PORT=int(os.environ.get("PORT","8080"))

def db():
    c=sqlite3.connect(DB); c.execute("""create table if not exists audits(
      id integer primary key, url text, created_at real, score integer, pages integer,
      issues integer, data text)"""); c.commit(); return c

class Parser(HTMLParser):
    def __init__(self, base):
        super().__init__(); self.base=base; self.title=""; self.meta={}; self.h1=0; self.h2=0
        self.images=0; self.no_alt=0; self.links=[]; self.words=0; self.in_title=False
        self.skip=0; self.buf=[]
    def handle_starttag(self,t,a):
        d=dict(a)
        if t in ("script","style","noscript"): self.skip+=1
        if t=="title": self.in_title=True
        if t=="meta" and d.get("name","").lower() in ("description","robots"):
            self.meta[d.get("name","").lower()]=d.get("content","")
        if t=="link" and d.get("rel","").lower()=="canonical": self.meta["canonical"]=d.get("href","")
        if t=="h1": self.h1+=1
        if t=="h2": self.h2+=1
        if t=="img":
            self.images+=1
            if not d.get("alt"): self.no_alt+=1
        if t=="a" and d.get("href"):
            u=urllib.parse.urljoin(self.base,d["href"]).split("#")[0]
            self.links.append(u)
    def handle_endtag(self,t):
        if t in ("script","style","noscript") and self.skip: self.skip-=1
        if t=="title": self.in_title=False
    def handle_data(self,data):
        if self.skip:return
        if self.in_title:self.title+=data.strip()+" "
        self.words += len(re.findall(r"\b[\wÀ-ÿ'-]+\b",data))

def fetch(url, timeout=12):
    req=urllib.request.Request(url,headers={"User-Agent":"SEO-Autopilot-Bot/1.0 (+audit)"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.getcode(), r.geturl(), r.read(900000), r.headers.get("Content-Type","")

def audit(start,max_pages=25):
    p=urllib.parse.urlparse(start); root=f"{p.scheme}://{p.netloc}"
    q=deque([start]); seen=set(); pages=[]; issues=[]
    while q and len(pages)<max_pages:
        u=q.popleft()
        if u in seen: continue
        seen.add(u)
        try:
            status,final,body,ctype=fetch(u)
            item={"url":final,"status":status}
            if "text/html" not in ctype: pages.append(item); continue
            parser=Parser(final); parser.feed(body.decode("utf-8","ignore"))
            title=parser.title.strip(); desc=parser.meta.get("description","")
            item.update(title=title,description=desc,h1=parser.h1,h2=parser.h2,
                        images=parser.images,no_alt=parser.no_alt,words=parser.words,
                        links=len(parser.links),canonical=parser.meta.get("canonical",""))
            if not title: issues.append({"severity":"high","url":final,"type":"missing_title","message":"Missing page title"})
            elif len(title)<30 or len(title)>65: issues.append({"severity":"medium","url":final,"type":"title_length","message":"Title length may need optimization"})
            if not desc: issues.append({"severity":"medium","url":final,"type":"missing_description","message":"Missing meta description"})
            if parser.h1==0: issues.append({"severity":"high","url":final,"type":"missing_h1","message":"No H1 heading found"})
            if parser.h1>1: issues.append({"severity":"medium","url":final,"type":"multiple_h1","message":"Multiple H1 headings"})
            if parser.no_alt: issues.append({"severity":"medium","url":final,"type":"image_alt","message":f"{parser.no_alt} images missing ALT"})
            if parser.words<300: issues.append({"severity":"low","url":final,"type":"thin_content","message":"Low visible word count"})
            pages.append(item)
            for link in parser.links:
                lp=urllib.parse.urlparse(link)
                if lp.netloc==p.netloc and lp.scheme in ("http","https") and link not in seen:
                    q.append(link)
        except Exception as e:
            issues.append({"severity":"high","url":u,"type":"crawl_error","message":str(e)[:140]})
    high=sum(x["severity"]=="high" for x in issues); med=sum(x["severity"]=="medium" for x in issues); low=sum(x["severity"]=="low" for x in issues)
    score=max(0, min(100, 100-high*7-med*3-low))
    opp=[]
    if high: opp.append({"priority":"HIGH","title":"Fix critical technical issues","detail":f"{high} high-impact issues detected."})
    if med: opp.append({"priority":"HIGH","title":"Optimize metadata and on-page structure","detail":f"{med} medium issues can be improved."})
    if any(x.get("links",0)<3 for x in pages): opp.append({"priority":"MEDIUM","title":"Strengthen internal linking","detail":"Some crawled pages have few internal links."})
    if any(x.get("words",0)<300 for x in pages): opp.append({"priority":"MEDIUM","title":"Expand thin pages where useful","detail":"Review low-content pages against search intent."})
    if not opp: opp.append({"priority":"MEDIUM","title":"Connect Search Console","detail":"Search data enables opportunity discovery based on impressions and positions."})
    result={"url":start,"score":score,"pages":pages,"issues":issues,"opportunities":opp,
            "summary":{"pages":len(pages),"issues":len(issues),"high":high,"medium":med,"low":low}}
    c=db(); c.execute("insert into audits(url,created_at,score,pages,issues,data) values(?,?,?,?,?,?)",
                      (start,time.time(),score,len(pages),len(issues),json.dumps(result))); c.commit(); c.close()
    return result

class Handler(BaseHTTPRequestHandler):
    def send_json(self,obj,code=200):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Headers","Content-Type"); self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self): self.send_response(204); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Headers","Content-Type"); self.end_headers()
    def do_POST(self):
        if self.path!="/api/audit": return self.send_json({"error":"not found"},404)
        n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n) or b"{}")
        url=data.get("url","").strip()
        if not re.match(r"^https?://",url): url="https://"+url
        try:self.send_json(audit(url))
        except Exception as e:self.send_json({"error":str(e)},500)
    def do_GET(self):
        if self.path=="/api/health": return self.send_json({"ok":True,"service":"SEO Autopilot"})
        if self.path.startswith("/api/audits"):
            c=db(); rows=c.execute("select id,url,created_at,score,pages,issues from audits order by id desc limit 20").fetchall(); c.close()
            return self.send_json([dict(id=r[0],url=r[1],created_at=r[2],score=r[3],pages=r[4],issues=r[5]) for r in rows])
        if self.path == "/":
            return self.serve_file("index.html")
        if self.path.startswith("/assets/"):
            return self.serve_file(self.path.lstrip("/"))
        self.send_json({"error":"not found"},404)
    def serve_file(self, relpath):
        path=os.path.abspath(os.path.join(FRONTEND_DIR, relpath))
        if not path.startswith(os.path.abspath(FRONTEND_DIR)+os.sep) or not os.path.isfile(path):
            return self.send_json({"error":"not found"},404)
        with open(path,"rb") as f: data=f.read()
        self.send_response(200); self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)

if __name__=="__main__":
    os.makedirs(os.path.dirname(DB),exist_ok=True)
    db().close()
    print(f"SEO Autopilot: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()