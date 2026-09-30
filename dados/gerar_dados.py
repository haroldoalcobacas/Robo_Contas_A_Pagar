import os, re, random, email.utils
from email.message import EmailMessage
from datetime import datetime, timedelta
from pathlib import Path
random.seed(42)
OUT=Path(__file__).resolve().parent/"caixa_de_entrada"
OUT.mkdir(exist_ok=True)
BASE=datetime(2026,9,1,9,0)
fornecedores=[
 ("Nuvem Hosting Ltda","12.345.678/0001-90","financeiro@nuvemhosting.com.br","Hospedagem e servidores"),
 ("Papelaria Central ME","23.456.789/0001-01","nf@papelariacentral.com.br","Material de escritório"),
 ("Contabilidade Silva & Filhos","34.567.890/0001-12","contato@silvacontabil.com.br","Honorários contábeis"),
 ("Energia Paulista S.A.","45.678.901/0001-23","nao-responda@energiapaulista.com.br","Conta de energia"),
 ("TechSoft Licenças Ltda","56.789.012/0001-34","billing@techsoft.com.br","Licença de software"),
 ("Limpa Bem Serviços","67.890.123/0001-45","limpabem.servicos@gmail.com","Serviço de limpeza"),
]
def nfe_xml(num, forn, valor, emissao, venc, itens):
    nome,cnpj,_,_=forn
    c=cnpj.replace(".","").replace("/","").replace("-","")
    det="".join(f"""
      <det nItem="{i+1}"><prod><cProd>{i+1:03d}</cProd><xProd>{d}</xProd><qCom>{q}</qCom><vUnCom>{u:.2f}</vUnCom><vProd>{q*u:.2f}</vProd></prod></det>""" for i,(d,q,u) in enumerate(itens))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe35{emissao:%y%m}{c}55001{num:09d}1" versao="4.00">
    <ide><nNF>{num}</nNF><serie>1</serie><dhEmi>{emissao:%Y-%m-%dT%H:%M:%S}-03:00</dhEmi></ide>
    <emit><CNPJ>{c}</CNPJ><xNome>{nome}</xNome></emit>
    <dest><CNPJ>98765432000100</CNPJ><xNome>Sua Empresa Ltda</xNome></dest>{det}
    <total><ICMSTot><vNF>{valor:.2f}</vNF></ICMSTot></total>
    <cobr><dup><nDup>001</nDup><dVenc>{venc:%Y-%m-%d}</dVenc><vDup>{valor:.2f}</vDup></dup></cobr>
  </infNFe></NFe>
</nfeProc>
""".encode()
def pdf(lines):
    # PDF mínimo com texto (Helvetica, sem acentos)
    content="BT /F1 11 Tf 50 780 Td 14 TL\n"+"".join(f"({l.replace('(','[').replace(')',']')}) '\n" for l in lines)+"ET"
    objs=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
      f"<< /Length {len(content)} >>\nstream\n{content}\nendstream","<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out=b"%PDF-1.4\n"; offs=[]
    for i,o in enumerate(objs):
        offs.append(len(out)); out+=f"{i+1} 0 obj\n{o}\nendobj\n".encode("latin-1")
    x=len(out); out+=f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()+"".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    out+=f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode(); return out
def brl(v): return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
msgs=[]
def mail(n, frm, subj, body, dt, atts=()):
    m=EmailMessage(); m["From"]=frm; m["To"]="contas@suaempresa.com.br"; m["Subject"]=subj
    m["Date"]=email.utils.format_datetime(dt); m.set_content(body)
    for fn,data,mt in atts:
        a,b=mt.split("/"); m.add_attachment(data,maintype=a,subtype=b,filename=fn)
    open(f"{OUT}/{n:02d}_{re.sub(r'[^A-Za-z0-9]+','_',subj.encode('ascii','ignore').decode())[:40].strip('_')}.eml","wb").write(bytes(m))
n=0
# XML NF-e normais
for k,(fi,valor,dd,vd) in enumerate([(0,489.90,1,15),(1,213.47,3,20),(2,1850.00,5,10),(4,3200.00,8,30),(1,97.30,12,27),(0,489.90,15,30)]):
    n+=1; f=fornecedores[fi]; em=BASE+timedelta(days=dd); ve=BASE+timedelta(days=vd)
    num=1000+k*37; itens=[(f[3],1,valor)] if fi!=1 else [("Resma papel A4",3,round(valor*0.5/3,2)),("Canetas e diversos",1,round(valor-3*round(valor*0.5/3,2),2))]
    mail(n,f"{f[0]} <{f[2]}>",f"NF-e {num} - {f[0]}",f"Prezados,\n\nSegue em anexo a NF-e {num}.\n\nAtt,\n{f[0]}",em,[(f"NFe_{num}.xml",nfe_xml(num,f,valor,em,ve,itens),"application/xml")])
# NF duplicada (reenvio da mesma nota)
n+=1; f=fornecedores[1]; em=BASE+timedelta(days=3); ve=BASE+timedelta(days=20)
mail(n,f"{f[0]} <{f[2]}>","RE: NF-e 1037 - Papelaria Central ME","Reenviando conforme solicitado.",BASE+timedelta(days=6),[("NFe_1037.xml",nfe_xml(1037,f,213.47,em,ve,[("Resma papel A4",3,35.58),("Canetas e diversos",1,106.73)]),"application/xml")])
# Boletos/faturas em PDF (sem XML)
for fi,valor,dd,vd,cod in [(3,742.18,4,18,"83660000007-4 42180138000-1 00000000000-1 20260919000-0"),(5,1200.00,9,25,"34191.79001 01043.510047 91020.150008 1 99990000120000")]:
    n+=1; f=fornecedores[fi]; em=BASE+timedelta(days=dd); ve=BASE+timedelta(days=vd)
    linhas=[f[0].encode('ascii','ignore').decode(),f"CNPJ: {f[1]}","",f"Fatura / Boleto - {f[3]}".encode('ascii','ignore').decode(),f"Referencia: 09/2026",f"Vencimento: {ve:%d/%m/%Y}",f"Valor do documento: {brl(valor)}",f"Linha digitavel: {cod}"]
    mail(n,f"{f[0]} <{f[2]}>",f"Sua fatura chegou - vencimento {ve:%d/%m}",f"Olá!\n\nSua fatura de {ve:%m/%Y} está disponível em anexo.\nValor: {brl(valor)}\nVencimento: {ve:%d/%m/%Y}",em,[(f"fatura_{ve:%Y%m}.pdf",pdf(linhas),"application/pdf")])
# Fatura só no corpo do e-mail (sem anexo)
n+=1; f=fornecedores[4]; ve=BASE+timedelta(days=5)
mail(n,f"{f[0]} <{f[2]}>","Lembrete: fatura em aberto",f"Olá,\n\nIdentificamos a fatura TS-2026-0917 em aberto.\nValor: {brl(349.00)}\nVencimento: {ve:%d/%m/%Y}\n\nCaso já tenha pago, desconsidere.",BASE+timedelta(days=2))
# Ruído: newsletter, e-mail pessoal, anexo que não é nota
n+=1; mail(n,"Newsletter RPA Brasil <news@rpabrasil.com.br>","5 tendências de automação para 2027","Confira as tendências...",BASE+timedelta(days=7))
n+=1; mail(n,"Joana <joana@suaempresa.com.br>","Almoço sexta?","Bora almoçar sexta?",BASE+timedelta(days=10))
n+=1; mail(n,"RH <rh@suaempresa.com.br>","Política de férias atualizada","Segue a política.",BASE+timedelta(days=11),[("politica_ferias.pdf",pdf(["Politica de ferias 2026","Documento interno"]),"application/pdf")])
# XML corrompido
n+=1; f=fornecedores[2]; mail(n,f"{f[0]} <{f[2]}>","NF-e 1111 - Contabilidade Silva & Filhos","Segue NF.",BASE+timedelta(days=13),[("NFe_1111.xml",nfe_xml(1111,f,1850.00,BASE,BASE+timedelta(days=40),[(f[3],1,1850.0)])[:400],"application/xml")])
print(n,"emails")
