import base64,json,logging,os,requests
from flask import Flask,request,jsonify,send_file,Response

app=Flask(__name__)
logging.basicConfig(level=logging.INFO,format="%(asctime)s [%(levelname)s] %(message)s")
log=logging.getLogger("gaucha")

ALEGRA_USER=os.environ.get("ALEGRA_USER","gauchasantateresa@gmail.com")
ALEGRA_TOKEN=os.environ.get("ALEGRA_TOKEN","547e9754350c6ec61e81")
WEBHOOK_SECRET=os.environ.get("WEBHOOK_SECRET","gaucha2026")
CABYS="5611001001000"
NOMBRE_SERVICIO="Servicio de Restaurante"
ALEGRA_API="https://api.alegra.com/api/prime/v1"
TARJETA_KW=["tarjeta","card","visa","mastercard","amex","credito","debito"]
_item_id=None

def alegra_h():
    c=base64.b64encode(f"{ALEGRA_USER}:{ALEGRA_TOKEN}".encode()).decode()
    return {"Authorization":f"Basic {c}","Content-Type":"application/json"}

def get_item():
    global _item_id
    if _item_id:return _item_id
    r=requests.get(f"{ALEGRA_API}/items",headers=alegra_h(),params={"name":NOMBRE_SERVICIO},timeout=15)
    if r.status_code==200:
        items=r.json()
        if isinstance(items,list)and items:_item_id=items[0]["id"];return _item_id
    p={"name":NOMBRE_SERVICIO,"price":1000,"tax":[{"id":5}],"reference":CABYS,"type":"service"}
    r=requests.post(f"{ALEGRA_API}/items",headers=alegra_h(),json=p,timeout=15)
    if r.status_code in(200,201):_item_id=r.json()["id"];return _item_id
    return None

def emitir(monto,fecha,ref):
    iid=get_item()
    if not iid:return{"ok":False,"error":"No item Alegra"}
    p={"date":str(fecha)[:10],"dueDate":str(fecha)[:10],"paymentType":"cash","type":"04",
       "stamp":{"generateStamp":True},
       "items":[{"id":iid,"name":NOMBRE_SERVICIO,"quantity":1,"price":round(monto/1.13,5),"tax":[{"id":5}],"reference":CABYS}],
       "notes":f"Ref: {ref}"}
    r=requests.post(f"{ALEGRA_API}/invoices",headers=alegra_h(),json=p,timeout=30)
    if r.status_code in(200,201):
        d=r.json()
        return{"ok":True,"numero_alegra":d.get("id"),"consecutivo":d.get("numberTemplate",{}).get("fullNumber",""),"clave":(d.get("stamp")or{}).get("electronicInvoiceId","")}
    return{"ok":False,"error":r.json().get("message",r.text[:200])}

@app.route("/")
def health():return jsonify({"status":"ok","service":"Gaucha Sur FE"})

@app.route("/script")
def script():
    with open("gaucha_tiquetes.js") as f:content=f.read()
    return Response(content,mimetype="application/javascript",headers={"Access-Control-Allow-Origin":"*","Cache-Control":"no-cache"})

@app.route("/instalar")
def instalar():return send_file("instalar.html")

@app.route("/app")
def app_page():return send_file("app_odoo.html")

@app.route("/webhook",methods=["POST"])
def webhook():
    if request.headers.get("X-Webhook-Secret","")!=WEBHOOK_SECRET:return jsonify({"error":"Unauthorized"}),401
    d=request.get_json(force=True,silent=True)or{}
    name=d.get("name","N/A");amount=float(d.get("amount_total",0));date=d.get("date_order","")
    method=d.get("payment_method_name","").lower();state=d.get("state","")
    if state not in("done","invoiced","paid"):return jsonify({"status":"skipped","reason":f"Estado {state}"})
    if not any(k in method for k in TARJETA_KW):return jsonify({"status":"skipped","reason":"No tarjeta"})
    if amount<=0:return jsonify({"status":"skipped","reason":"Monto inválido"})
    r=emitir(amount,date,name)
    if r["ok"]:return jsonify({"status":"ok","orden":name,**r})
    return jsonify({"status":"error","message":r["error"]}),500

@app.route("/test",methods=["POST"])
def test():
    if request.headers.get("X-Webhook-Secret","")!=WEBHOOK_SECRET:return jsonify({"error":"Unauthorized"}),401
    d=request.get_json(force=True,silent=True)or{}
    return jsonify(emitir(float(d.get("monto",10000)),d.get("fecha","2026-06-02"),d.get("referencia","TEST")))

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
