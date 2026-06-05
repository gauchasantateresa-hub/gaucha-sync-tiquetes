"""
Módulo 3: Firmador XAdES-EPES para Hacienda CR v4.4
Fix: los digests de KeyInfo y SignedProperties se calculan
     en el contexto correcto del documento (con namespaces heredados)
"""
import base64, hashlib
from datetime import datetime
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

POLITICA_URL    = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/Resoluci%C3%B3n_General_sobre_disposiciones_t%C3%A9cnicas_comprobantes_electr%C3%B3nicos_para_efectos_tributarios.pdf"
POLITICA_DIGEST = "DWxin1xWOeI8OuWQXazh4VjLWAaCLAA954em7DMh0h8="

NODOS_NS = {
    "01": "facturaElectronica",    "02": "notaDebitoElectronica",
    "03": "notaCreditoElectronica","04": "tiqueteElectronico",
    "05": "mensajeReceptor",       "06": "mensajeReceptor",
    "07": "mensajeReceptor",
}
NS_BASE = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/"
NS_DS   = "http://www.w3.org/2000/09/xmldsig#"
NS_XSI  = "http://www.w3.org/2001/XMLSchema-instance"
NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"

SIG_ID          = "Signature-ddb543c7-ea0c-4b00-95b9-d4bfa2b4e411"
SIG_VAL_ID      = "SignatureValue-ddb543c7-ea0c-4b00-95b9-d4bfa2b4e411"
XOBJ_ID         = "XadesObjectId-43208d10-650c-4f42-af80-fc889962c9ac"
KEYINFO_ID      = f"KeyInfoId-{SIG_ID}"
REF0_ID         = "Reference-0e79b719-635c-476f-a59e-8ac3ba14365d"
REF1_ID         = "ReferenceKeyInfo"
SIGNED_PROPS_ID = f"SignedProperties-{SIG_ID}"


def _c14n_node(node) -> bytes:
    """C14N de un nodo lxml (hereda namespaces del contexto)."""
    return etree.tostring(node, method="c14n")


def _c14n_fragment(xml_str: str) -> bytes:
    """C14N de un fragmento XML standalone."""
    doc = etree.fromstring(xml_str.encode("utf-8"))
    return etree.tostring(doc, method="c14n")


def _sha256_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def _oid_name(oid):
    nombres = {
        "2.5.4.3":"CN","2.5.4.6":"C","2.5.4.7":"L","2.5.4.8":"ST",
        "2.5.4.10":"O","2.5.4.11":"OU","2.5.4.5":"serialNumber",
        "1.2.840.113549.1.9.1":"emailAddress",
    }
    return nombres.get(oid.dotted_string, oid.dotted_string)


def firmar(p12_path: str, pin: str, xml_sin_firma: bytes, tipo_doc: str = "04") -> bytes:
    """
    Firma el XML con XAdES-EPES usando el certificado .p12 de Hacienda CR.
    
    Estrategia correcta:
    1. C14N del XML original → digest del documento
    2. Construir KeyInfo y SignedProperties como strings
    3. Insertar el Signature completo (con placeholders para digests)
    4. Parsear el XML con firma → calcular digests de KeyInfo y SignedProperties
       en el contexto real del documento (así coinciden con lo que Hacienda verifica)
    5. Construir SignedInfo con los digests correctos → firmar → reemplazar
    """

    # ── 1. Cargar certificado ─────────────────────────────────────────────────
    with open(p12_path, "rb") as f:
        p12_data = f.read()

    private_key, cert, _ = pkcs12.load_key_and_certificates(p12_data, pin.encode())

    cert_der  = cert.public_bytes(Encoding.DER)
    cert_pem  = cert.public_bytes(Encoding.PEM).decode()
    cert_pem_clean = (cert_pem
                      .replace("-----BEGIN CERTIFICATE-----","")
                      .replace("-----END CERTIFICATE-----","")
                      .replace("\n","").replace("\r","").strip())
    cert_digest = _sha256_b64(cert_der)

    # Issuer DN en orden inverso
    issuer_parts = []
    for attr in reversed(list(cert.issuer)):
        issuer_parts.append(f"{_oid_name(attr.oid)}={attr.value}")
    cert_issuer = ", ".join(issuer_parts)
    serial_number = str(cert.serial_number)

    # Módulo y exponente RSA
    pub = private_key.public_key().public_numbers()
    modulus_b64  = base64.b64encode(pub.n.to_bytes((pub.n.bit_length()+7)//8,"big")).decode()
    exponent_b64 = base64.b64encode(pub.e.to_bytes((pub.e.bit_length()+7)//8,"big")).decode()

    # ── 2. Namespace del documento ────────────────────────────────────────────
    NS_DOC = NS_BASE + NODOS_NS.get(tipo_doc, "tiqueteElectronico")
    TAG_RAIZ = {
        "01":"FacturaElectronica","02":"NotaDebitoElectronica",
        "03":"NotaCreditoElectronica","04":"TiqueteElectronico",
        "05":"MensajeReceptor","06":"MensajeReceptor","07":"MensajeReceptor",
    }.get(tipo_doc, "TiqueteElectronico")

    # ── 3. Digest del documento original ─────────────────────────────────────
    doc_orig  = etree.fromstring(xml_sin_firma)
    c14n_orig = _c14n_node(doc_orig)
    doc_digest = _sha256_b64(c14n_orig)

    # ── 4. Strings de KeyInfo y SignedProperties ──────────────────────────────
    sign_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00")

    k_info_str = f'''<ds:KeyInfo Id="{KEYINFO_ID}">
<ds:X509Data>
<ds:X509Certificate>{cert_pem_clean}</ds:X509Certificate>
</ds:X509Data>
<ds:KeyValue>
<ds:RSAKeyValue>
<ds:Modulus>{modulus_b64}</ds:Modulus>
<ds:Exponent>{exponent_b64}</ds:Exponent>
</ds:RSAKeyValue>
</ds:KeyValue>
</ds:KeyInfo>'''

    prop_str = f'''<xades:SignedProperties Id="{SIGNED_PROPS_ID}">
<xades:SignedSignatureProperties>
<xades:SigningTime>{sign_time}</xades:SigningTime>
<xades:SigningCertificate>
<xades:Cert>
<xades:CertDigest>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{cert_digest}</ds:DigestValue>
</xades:CertDigest>
<xades:IssuerSerial>
<ds:X509IssuerName>{cert_issuer}</ds:X509IssuerName>
<ds:X509SerialNumber>{serial_number}</ds:X509SerialNumber>
</xades:IssuerSerial>
</xades:Cert>
</xades:SigningCertificate>
<xades:SignaturePolicyIdentifier>
<xades:SignaturePolicyId>
<xades:SigPolicyId>
<xades:Identifier>{POLITICA_URL}</xades:Identifier>
<xades:Description/>
</xades:SigPolicyId>
<xades:SigPolicyHash>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{POLITICA_DIGEST}</ds:DigestValue>
</xades:SigPolicyHash>
</xades:SignaturePolicyId>
</xades:SignaturePolicyIdentifier>
<xades:SignerRole>
<xades:ClaimedRoles>
<xades:ClaimedRole>Emisor</xades:ClaimedRole>
</xades:ClaimedRoles>
</xades:SignerRole>
</xades:SignedSignatureProperties>
<xades:SignedDataObjectProperties>
<xades:DataObjectFormat ObjectReference="#{REF0_ID}">
<xades:MimeType>text/xml</xades:MimeType>
<xades:Encoding>UTF-8</xades:Encoding>
</xades:DataObjectFormat>
</xades:SignedDataObjectProperties>
</xades:SignedProperties>'''

    # ── 5. Insertar un Signature temporal (con placeholders) ──────────────────
    # para que KeyInfo y SignedProperties hereden los namespaces correctos
    sig_temp = f'''<ds:Signature xmlns:ds="{NS_DS}" Id="{SIG_ID}">
<ds:SignedInfo>PLACEHOLDER_SIGNED_INFO</ds:SignedInfo>
<ds:SignatureValue Id="{SIG_VAL_ID}">PLACEHOLDER_SIG_VALUE</ds:SignatureValue>
{k_info_str}
<ds:Object Id="{XOBJ_ID}">
<xades:QualifyingProperties xmlns:xades="{NS_XADES}" Target="#{SIG_ID}">
{prop_str}
</xades:QualifyingProperties>
</ds:Object>
</ds:Signature>'''

    xml_str = xml_sin_firma.decode("utf-8")
    xml_con_sig_temp = xml_str.replace(f"</{TAG_RAIZ}>", sig_temp + f"\n</{TAG_RAIZ}>")

    # ── 6. Parsear y calcular digests de KeyInfo y SignedProperties ───────────
    # Ahora los nodos heredan namespaces correctamente del documento padre
    doc_temp = etree.fromstring(xml_con_sig_temp.encode("utf-8"))

    keyinfo_node = doc_temp.find(f'.//{{{NS_DS}}}KeyInfo')
    props_node   = doc_temp.find(f'.//{{{NS_XADES}}}SignedProperties')

    kinfo_digest = _sha256_b64(_c14n_node(keyinfo_node))
    prop_digest  = _sha256_b64(_c14n_node(props_node))

    # ── 7. Construir SignedInfo con digests correctos ─────────────────────────
    signed_info_str = f'''<ds:SignedInfo xmlns:ds="{NS_DS}" xmlns="{NS_DOC}" xmlns:xsi="{NS_XSI}">
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
<ds:Reference Id="{REF0_ID}" URI="">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{doc_digest}</ds:DigestValue>
</ds:Reference>
<ds:Reference Id="{REF1_ID}" URI="#{KEYINFO_ID}">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{kinfo_digest}</ds:DigestValue>
</ds:Reference>
<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#{SIGNED_PROPS_ID}">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{prop_digest}</ds:DigestValue>
</ds:Reference>
</ds:SignedInfo>'''

    # C14N del SignedInfo para firmar
    signed_info_c14n = _c14n_fragment(signed_info_str)

    # ── 8. Firma RSA-SHA256 ───────────────────────────────────────────────────
    firma_bytes = private_key.sign(signed_info_c14n, padding.PKCS1v15(), hashes.SHA256())
    firma_b64   = base64.b64encode(firma_bytes).decode()

    # ── 9. Bloque Signature final ─────────────────────────────────────────────
    # NOTA: el SignedInfo aquí va SIN los namespaces extra (los heredará del contexto)
    signed_info_inner = f'''<ds:SignedInfo>
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
<ds:Reference Id="{REF0_ID}" URI="">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{doc_digest}</ds:DigestValue>
</ds:Reference>
<ds:Reference Id="{REF1_ID}" URI="#{KEYINFO_ID}">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{kinfo_digest}</ds:DigestValue>
</ds:Reference>
<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#{SIGNED_PROPS_ID}">
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{prop_digest}</ds:DigestValue>
</ds:Reference>
</ds:SignedInfo>'''

    sig_final = f'''<ds:Signature xmlns:ds="{NS_DS}" Id="{SIG_ID}">
{signed_info_inner}
<ds:SignatureValue Id="{SIG_VAL_ID}">{firma_b64}</ds:SignatureValue>
{k_info_str}
<ds:Object Id="{XOBJ_ID}">
<xades:QualifyingProperties xmlns:xades="{NS_XADES}" Target="#{SIG_ID}">
{prop_str}
</xades:QualifyingProperties>
</ds:Object>
</ds:Signature>'''

    xml_firmado = xml_str.replace(f"</{TAG_RAIZ}>", sig_final + f"\n</{TAG_RAIZ}>")
    return xml_firmado.encode("utf-8")


if __name__ == "__main__":
    import os
    from xml_generator import generar_xml

    p12 = "/mnt/user-data/uploads/certificado1__1_.p12"
    xml = generar_xml(
        clave="50605062600310280744200100001040000000099999999999",
        consecutivo="00100001040000000099",
        fecha_emision=datetime(2026, 6, 5, 12, 0, 0),
        emisor_nombre="Tres Bochas Sociedad De Responsabilidad Limitada",
        emisor_tipo_id="02", emisor_num_id="3102807442",
        emisor_provincia="6", emisor_canton="01", emisor_distrito="01",
        emisor_otras_senas="Frente Antigua Discoteca Lora Amarilla, Santa Teresa",
        emisor_email="gauchasantateresa@gmail.com", emisor_telefono="60000000",
        actividad_economica="5610000",
        descripcion="Servicio de Restaurante", cantidad=1, unidad_medida="Sp",
        precio_unitario=round(3850/1.13, 5), cabys="6331000000000", porcentaje_iva=13.0
    )

    xf = firmar(p12, "5561", xml, "04")
    print(f"✅ XML firmado: {len(xf)} bytes")

    # Verificar que los digests son correctos
    from lxml import etree
    doc = etree.fromstring(xf)
    NS_DS_V = 'http://www.w3.org/2000/09/xmldsig#'
    NS_XADES_V = 'http://uri.etsi.org/01903/v1.3.2#'

    ki = doc.find(f'.//{{{NS_DS_V}}}KeyInfo')
    sp = doc.find(f'.//{{{NS_XADES_V}}}SignedProperties')

    ki_c14n = etree.tostring(ki, method="c14n")
    sp_c14n = etree.tostring(sp, method="c14n")

    ki_digest_real = base64.b64encode(hashlib.sha256(ki_c14n).digest()).decode()
    sp_digest_real = base64.b64encode(hashlib.sha256(sp_c14n).digest()).decode()

    refs = doc.findall(f'.//{{{NS_DS_V}}}Reference')
    for ref in refs:
        dv = ref.find(f'{{{NS_DS_V}}}DigestValue')
        uri = ref.get('URI', '')
        if 'KeyInfo' in uri and dv is not None:
            match = "✅" if dv.text == ki_digest_real else "❌"
            print(f"KeyInfo digest: {match} ({dv.text[:20]}... vs {ki_digest_real[:20]}...)")
        elif 'SignedProperties' in uri and dv is not None:
            match = "✅" if dv.text == sp_digest_real else "❌"
            print(f"SignedProps digest: {match} ({dv.text[:20]}... vs {sp_digest_real[:20]}...)")
