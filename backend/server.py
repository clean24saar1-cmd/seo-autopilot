import base64, hashlib, hmac, json, os, re, secrets, sqlite3, time, urllib.parse, urllib.request, urllib.error, urllib.robotparser, mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from collections import deque, Counter

BASE_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB=os.path.join(BASE_DIR,"data","seo.db")
FRONTEND_DIR=os.path.join(BASE_DIR,"frontend")
PORT=int(os.environ.get("PORT","8080"))

def db():
    c=sqlite3.connect(DB); c.execute("""create table if not exists audits(
      id integer primary key, user_id integer, url text, created_at real, score integer, pages integer,
      issues integer, data text)""")
    c.execute("""create table if not exists users(
      id integer primary key, email text unique not null, password_hash text not null,
      salt text not null, plan text not null default 'free', stripe_customer_id text,
      stripe_subscription_id text, subscription_status text, created_at real)""")
    cols=[r[1] for r in c.execute("pragma table_info(audits)").fetchall()]
    if "user_id" not in cols:
        c.execute("alter table audits add column user_id integer")
    c.commit(); return c


PLANS={"free":{"name":"مجاني","audits":2,"pages":5},"starter":{"name":"Starter","audits":30,"pages":25},"pro":{"name":"Pro","audits":150,"pages":100},"agency":{"name":"Agency","audits":500,"pages":250}}
def hash_password(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt,hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),210000).hex()
def verify_password(password,salt,digest):
    return hmac.compare_digest(hash_password(password,salt)[1],digest)
def current_user(handler):
    m=re.search(r"(?:^|;\s*)session=([^;]+)",handler.headers.get("Cookie",""))
    if not m:return None
    try:
        raw=base64.urlsafe_b64decode(m.group(1)+"==").decode(); uid,mac=raw.split(".",1)
        secret=os.environ.get("SESSION_SECRET","change-this-secret")
        if not hmac.compare_digest(mac,hmac.new(secret.encode(),uid.encode(),hashlib.sha256).hexdigest()):return None
        c=db();r=c.execute("select id,email,plan,stripe_customer_id,stripe_subscription_id,subscription_status from users where id=?",(int(uid),)).fetchone();c.close()
        return {"id":r[0],"email":r[1],"plan":r[2],"stripe_customer_id":r[3],"stripe_subscription_id":r[4],"subscription_status":r[5]} if r else None
    except Exception:return None
def set_cookie(handler,uid):
    secret=os.environ.get("SESSION_SECRET","change-this-secret");mac=hmac.new(secret.encode(),str(uid).encode(),hashlib.sha256).hexdigest()
    token=base64.urlsafe_b64encode(f"{uid}.{mac}".encode()).decode().rstrip("=")
    handler.send_header("Set-Cookie",f"session={token}; Path=/; HttpOnly; SameSite=Lax; Secure")
def usage(uid):
    c=db();n=c.execute("select count(*) from audits where user_id=? and created_at>=?",(uid,time.time()-30*86400)).fetchone()[0];c.close();return n
def require_user(handler):
    u=current_user(handler)
    if not u: handler.send_json({"error":"login_required","message":"سجل الدخول أولاً."},401); return None
    return u

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

FIX_GUIDES = {
    "missing_title": {
        "fix": "أضف عنوان Title فريدًا يصف محتوى الصفحة.",
        "steps": ["افتح الصفحة أو قالبها.", "ضع عنوانًا واضحًا مرتبطًا بموضوع الصفحة والكلمة المستهدفة.", "استهدف عادةً عنوانًا مختصرًا وواضحًا، وتجنب تكرار العناوين بين الصفحات."],
        "example": "<title>خدمة تصميم مواقع احترافية | اسم الشركة</title>"
    },
    "title_length": {
        "fix": "أعد كتابة عنوان الصفحة ليكون أوضح وأكثر تركيزًا على نية البحث.",
        "steps": ["ضع الكلمة أو العبارة الرئيسية في مكان طبيعي.", "احذف الكلمات الزائدة والتكرار.", "راجع العنوان في نتائج البحث بعد النشر."],
        "example": "<title>أفضل خدمات SEO للمواقع | اسم الشركة</title>"
    },
    "missing_description": {
        "fix": "أضف Meta Description تلخص الصفحة وتشجع الباحث على فتحها.",
        "steps": ["اكتب وصفًا فريدًا للصفحة.", "اذكر موضوع الصفحة أو فائدتها بوضوح.", "تجنب نسخ نفس الوصف لكل الصفحات."],
        "example": "<meta name=\"description\" content=\"تعرف على خدمات SEO وتحسين المواقع لزيادة الظهور في محركات البحث.\">"
    },
    "missing_h1": {
        "fix": "أضف عنوان H1 واحدًا يعبّر عن الموضوع الرئيسي للصفحة.",
        "steps": ["حدد الموضوع الأساسي.", "أضف H1 واضحًا في المحتوى.", "تأكد أن العنوان يخدم نية البحث بدل حشو الكلمات."],
        "example": "<h1>خدمات تحسين محركات البحث SEO</h1>"
    },
    "multiple_h1": {
        "fix": "راجع عناوين H1 واجعل هناك عنوانًا رئيسيًا واضحًا واحدًا للصفحة.",
        "steps": ["احتفظ بـ H1 الذي يمثل الموضوع الرئيسي.", "حوّل العناوين الثانوية إلى H2 أو H3 عند الحاجة.", "تأكد من أن هيكل العناوين منطقي."],
        "example": "<h1>الموضوع الرئيسي</h1>\n<h2>القسم الأول</h2>"
    },
    "image_alt": {
        "fix": "أضف ALT وصفيًا للصور المهمة، واترك الصور الزخرفية بدون نص بديل عند الحاجة.",
        "steps": ["راجع كل صورة بلا ALT.", "اكتب وصفًا قصيرًا يشرح محتوى الصورة عندما تكون الصورة مفيدة.", "لا تحشو ALT بالكلمات المفتاحية."],
        "example": "<img src=\"image.webp\" alt=\"فريق تحسين محركات البحث يعمل على تحليل الموقع\">"
    },
    "thin_content": {
        "fix": "وسّع الصفحة فقط إذا كانت نية البحث تحتاج معلومات أكثر؛ لا تضف نصًا حشوًا.",
        "steps": ["حدد سؤال الزائر أو نية البحث.", "أضف معلومات أصلية وأمثلة وأسئلة شائعة عند الحاجة.", "حسّن قابلية القراءة والتنظيم والروابط الداخلية."],
        "example": "أضف أقسامًا مفيدة تجيب عن الأسئلة الفعلية للزائر بدل تكرار الكلمات المفتاحية."
    },
    "crawl_error": {
        "fix": "افحص سبب فشل الوصول إلى الصفحة أو المورد.",
        "steps": ["تأكد من أن الرابط صحيح ويستخدم HTTPS.", "افحص حالة الخادم وإعادة التوجيه وملف robots.txt.", "إذا كان المورد محميًا أو محذوفًا، أصلح الرابط أو استبدله."],
        "example": "HTTP 200 للصفحات العامة، مع إعادة توجيه 301 عند تغيير الرابط."
    }
}

def audit(start,user_id,max_pages=25):
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
    for item in issues:\n        item.update(FIX_GUIDES.get(item["type"], {"fix":"راجع السبب وأصلح المشكلة من مصدرها.","steps":["افحص الصفحة المتأثرة.","طبّق التعديل المناسب.","أعد تشغيل الفحص للتأكد من اختفاء المشكلة."],"example":""}))\n    action_plan=[]\n    for priority, label, types in [("1","تقني","crawl_error"),("2","On-Page","missing_title"),("3","On-Page","missing_description"),("4","محتوى","thin_content"),("5","ربط داخلي","internal_links")]:\n        if any(x.get("type")==types for x in issues): action_plan.append({"step":priority,"area":label,"action":next((x["fix"] for x in issues if x.get("type")==types),"")})\n    result={"url":start,"score":score,"pages":pages,"issues":issues,"opportunities":opp,"action_plan":action_plan,
            "summary":{"pages":len(pages),"issues":len(issues),"high":high,"medium":med,"low":low}}
    c=db(); c.execute("insert into audits(user_id,url,created_at,score,pages,issues,data) values(?,?,?,?,?,?,?)",
                      (user_id,start,time.time(),score,len(pages),len(issues),json.dumps(result)); c.commit(); c.close()
    return result

class Handler(BaseHTTPRequestHandler):
    def send_json(self,obj,code=200,cookie_uid=None):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Headers","Content-Type")
        if cookie_uid is not None:
            secret=os.environ.get("SESSION_SECRET","change-this-secret"); mac=hmac.new(secret.encode(),str(cookie_uid).encode(),hashlib.sha256).hexdigest()
            token=base64.urlsafe_b64encode(f"{cookie_uid}.{mac}".encode()).decode().rstrip("=")
            self.send_header("Set-Cookie",f"session={token}; Path=/; HttpOnly; SameSite=Lax; Secure")
        self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self): self.send_response(204); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Headers","Content-Type"); self.end_headers()
    def do_POST(self):
        path=urllib.parse.urlparse(self.path).path
        n=int(self.headers.get("Content-Length","0"))
        data=json.loads(self.rfile.read(n) or b"{}")
        if path=="/api/register":
            email=data.get("email","").strip().lower(); password=data.get("password","")
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$",email) or len(password)<8:
                return self.send_json({"error":"invalid","message":"أدخل بريدًا صحيحًا وكلمة مرور من 8 أحرف على الأقل."},400)
            salt,digest=hash_password(password); c=db()
            try:
                c.execute("insert into users(email,password_hash,salt,plan,created_at) values(?,?,?,?,?)",(email,digest,salt,"free",time.time())); c.commit()
                uid=c.execute("select id from users where email=?",(email,)).fetchone()[0]
            except sqlite3.IntegrityError:
                c.close(); return self.send_json({"error":"exists","message":"هذا البريد مسجل بالفعل."},409)
            c.close(); return self.send_json({"ok":True,"user":{"id":uid,"email":email,"plan":"free"}},cookie_uid=uid)
        if path=="/api/login":
            email=data.get("email","").strip().lower(); password=data.get("password",""); c=db()
            r=c.execute("select id,email,password_hash,salt,plan,stripe_customer_id,stripe_subscription_id,subscription_status from users where email=?",(email,)).fetchone(); c.close()
            if not r or not verify_password(password,r[3],r[2]): return self.send_json({"error":"invalid","message":"البريد أو كلمة المرور غير صحيحة."},401)
            return self.send_json({"ok":True,"user":{"id":r[0],"email":r[1],"plan":r[4],"stripe_customer_id":r[5],"stripe_subscription_id":r[6],"subscription_status":r[7]}},cookie_uid=r[0])
        if path=="/api/logout":
            self.send_response(200); self.send_header("Set-Cookie","session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax; Secure"); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b'{"ok":true}'); return
        if path=="/api/checkout":
            u=require_user(self)
            if not u:return
            plan_name=data.get("plan","")
            price=os.environ.get({"starter":"STRIPE_PRICE_STARTER","pro":"STRIPE_PRICE_PRO","agency":"STRIPE_PRICE_AGENCY"}.get(plan_name,""),"")
            key=os.environ.get("STRIPE_SECRET_KEY","")
            if not price or not key:
                return self.send_json({"error":"billing_not_configured","message":"الدفع يحتاج ربط Stripe: STRIPE_SECRET_KEY وStripe Price IDs في Render."},503)
            base=os.environ.get("APP_URL","").rstrip("/") or ("https://"+self.headers.get("Host",""))
            payload=urllib.parse.urlencode({"mode":"subscription","line_items[0][price]":price,"line_items[0][quantity]":"1","success_url":base+"/?checkout=success","cancel_url":base+"/?checkout=cancel","client_reference_id":str(u["id"]),"customer_email":u["email"],"metadata[user_id]":str(u["id"]),"metadata[plan]":plan_name,"subscription_data[metadata][user_id]":str(u["id"]),"subscription_data[metadata][plan]":plan_name}).encode()
            req=urllib.request.Request("https://api.stripe.com/v1/checkout/sessions",data=payload,method="POST",headers={"Authorization":"Bearer "+key,"Content-Type":"application/x-www-form-urlencoded"})
            try:
                with urllib.request.urlopen(req,timeout=20) as resp: checkout=json.loads(resp.read().decode())
                return self.send_json({"url":checkout["url"]})
            except urllib.error.HTTPError as e:
                return self.send_json({"error":"stripe_error","message":e.read().decode()[:500]},500)
        if path=="/api/stripe/webhook":
            raw=self.rfile.read(n); secret=os.environ.get("STRIPE_WEBHOOK_SECRET",""); sig=self.headers.get("Stripe-Signature","")
            if not secret:return self.send_json({"error":"webhook_not_configured"},503)
            try:
                parts=dict(x.split("=",1) for x in sig.split(",") if "=" in x); ts=parts.get("t",""); v1=parts.get("v1","")
                expected=hmac.new(secret.encode(),(ts+"."+raw.decode()).encode(),hashlib.sha256).hexdigest()
                if not ts or not v1 or not hmac.compare_digest(expected,v1) or abs(time.time()-int(ts))>300:raise ValueError("Invalid signature")
                event=json.loads(raw); typ=event.get("type",""); obj=event.get("data",{}).get("object",{}); meta=obj.get("metadata",{})
                uid=meta.get("user_id") or obj.get("client_reference_id"); plan=meta.get("plan","free")
                if uid:
                    c=db()
                    if typ=="checkout.session.completed":
                        c.execute("update users set plan=?,stripe_customer_id=?,stripe_subscription_id=?,subscription_status=? where id=?",(plan,obj.get("customer"),obj.get("subscription"),"active",int(uid)))
                    elif typ in ("customer.subscription.updated","customer.subscription.deleted"):
                        status=obj.get("status",""); c.execute("update users set plan=?,stripe_customer_id=?,stripe_subscription_id=?,subscription_status=? where id=?",(plan if status in ("active","trialing") else "free",obj.get("customer"),obj.get("id"),status,int(uid)))
                    c.commit();c.close()
                return self.send_json({"received":True})
            except Exception as e:return self.send_json({"error":"invalid_webhook","message":str(e)},400)
        if path=="/api/audit":
            u=require_user(self)
            if not u:return
            plan=PLANS.get(u["plan"],PLANS["free"]); used=usage(u["id"])
            if used>=plan["audits"]:
                return self.send_json({"error":"limit","message":f"انتهى حد خطة {plan['name']} لهذا الشهر ({plan['audits']} تحليلات). اختر اشتراكًا للمتابعة.","used":used,"limit":plan["audits"]},402)
            url=data.get("url","").strip()
            if not re.match(r"^https?://",url): url="https://"+url
            try:self.send_json(audit(url,u["id"],plan["pages"]))
            except Exception as e:self.send_json({"error":str(e)},500)
            return
        return self.send_json({"error":"not found"},404)
    def do_GET(self):
        path=urllib.parse.urlparse(self.path).path
        if path=="/api/health": return self.send_json({"ok":True,"service":"SEO Autopilot"})
        if path=="/api/me":
            u=current_user(self); return self.send_json({"user":u,"usage":usage(u["id"]) if u else 0,"plans":PLANS})
        if path.startswith("/api/audits"):
            u=require_user(self)
            if not u:return
            c=db(); rows=c.execute("select id,url,created_at,score,pages,issues from audits where user_id=? order by id desc limit 20",(u["id"],)).fetchall(); c.close()
            return self.send_json([dict(id=r[0],url=r[1],created_at=r[2],score=r[3],pages=r[4],issues=r[5]) for r in rows])
        if path == "/":
            return self.serve_file("index.html")
        if path.startswith("/assets/"):
            return self.serve_file(path.lstrip("/"))
        # Keep the public site usable for harmless URL variations such as /?x=1 or trailing paths.
        if not path.startswith("/api/"):
            return self.serve_file("index.html")
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