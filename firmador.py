"""
Módulo 3: Firmador XAdES-EPES para Hacienda CR v4.4
Fix basado en XML aceptado real de Hacienda:
- References del KeyInfo y SignedProperties incluyen <ds:Transform C14N> explícito
- CertDigest usa SHA1 (no SHA256)
- SigPolicyHash usa SHA1
- xmlns:xsd en el documento raíz
"""
import base64, hashlib
from datetime import datetime
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

# URLs y constantes
POLITICA_URL    = "https://tribunet.hacienda.go.cr/docs/esquemas/2016/v4.2/ResolucionComprobantesElectronicosDGT-R-48-2016_4.2.pdf"
POLITICA_DIGEST_SHA1 = "iA3sKANkD9LNjhHtbgg45Aw7/Fw="  # SHA1 de la política

NODOS_NS = {
    "01": "facturaElectronica",    "02": "notaDebitoElectronica",
    "03": "notaCreditoElectronica","04": "tiqueteElectronico",
    "05": "mensajeReceptor",       "06": "mensajeReceptor",
    "07": "mensajeReceptor",
}
NS_BASE  = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/"
NS_DS    = "http://www.w3.org/2000/09/xmldsig#"
NS_XSI   = "http://www.w3.org/2001/XMLSchema-instance"
NS_XSD   = "http://www.w3.org/2001/XMLSchema"
NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"
NS_XADES141 = "http://uri.etsi.org/01903/v1.4.1#"

SIG_ID          = "xmldsig-gaucha-0001"
KEYINFO_ID      = f"{SIG_ID}-keyinfo"
REF0_ID         = f"{SIG_ID}-ref0"
SIGVAL_ID       = f"{SIG_ID}-sigvalue"
SIGNED_PROPS_ID = f"{SIG_ID}-signedprops"


def _c14n_node(node) -> bytes:
    return etree.tostring(node, method="c14n")

def _sha256_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()

def _sha1_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha1(data).digest()).decode()

def _c14n_fragment(xml_str: str) -> bytes:
    doc = etree.fromstring(xml_str.encode("utf-8"))
    return etree.tostring(doc, method="c14n")

def _oid_name(oid):
    nombres = {
        "2.5.4.3":"cn","2.5.4.6":"c","2.5.4.7":"l","2.5.4.8":"st",
        "2.5.4.10":"o","2.5.4.11":"ou","2.5.4.5":"serialNumber",
        "1.2.840.113549.1.9.1":"emailAddress",
    }
    return nombres.get(oid.dotted_string, oid.dotted_string)


def firmar(p12_path: str, pin: str, xml_sin_firma: bytes, tipo_doc: str = "04") -> bytes:
    # ── 1. Certificado ───────────────────────────────────────────────────────
    with open(p12_path, "rb") as f:
        p12_data = f.read()
    private_key, cert, _ = pkcs12.load_key_and_certificates(p12_data, pin.encode())

    cert_der = cert.public_bytes(Encoding.DER)
    cert_pem = cert.public_bytes(Encoding.PEM).decode()
    cert_pem_clean = (cert_pem
                      .replace("-----BEGIN CERTIFICATE-----","")
                      .replace("-----END CERTIFICATE-----","")
                      .replace("\n","").replace("\r","").strip())

    # SHA1 del certificado (como usa el XML aceptado)
    cert_digest_sha1 = _sha1_b64(cert_der)

    # Issuer en formato DN minúsculas como lo hace el XML aceptado
    issuer_parts = []
    for attr in reversed(list(cert.issuer)):
        issuer_parts.append(f"{_oid_name(attr.oid)}={attr.value}")
    cert_issuer = ",".join(issuer_parts)
    serial_number = str(cert.serial_number)

    # RSA key info
    pub = private_key.public_key().public_numbers()
    modulus_b64  = base64.b64encode(pub.n.to_bytes((pub.n.bit_length()+7)//8,"big")).decode()
    exponent_b64 = base64.b64encode(pub.e.to_bytes((pub.e.bit_length()+7)//8,"big")).decode()

    # ── 2. Namespace y tag raíz ───────────────────────────────────────────────
    NS_DOC = NS_BASE + NODOS_NS.get(tipo_doc, "tiqueteElectronico")
    TAG_RAIZ = {
        "01":"FacturaElectronica","02":"NotaDebitoElectronica",
        "03":"NotaCreditoElectronica","04":"TiqueteElectronico",
    }.get(tipo_doc, "TiqueteElectronico")

    # ── 3. Digest del documento original ─────────────────────────────────────
    doc_orig = etree.fromstring(xml_sin_firma)
    c14n_orig = _c14n_node(doc_orig)
    doc_digest = _sha256_b64(c14n_orig)

    # ── 4. Tiempo de firma ────────────────────────────────────────────────────
    sign_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000-06:00")

    # ── 5. Strings de KeyInfo y SignedProperties ──────────────────────────────
    k_info_str = f'''<ds:KeyInfo Id="{KEYINFO_ID}">
<ds:X509Data>
<ds:X509Certificate>
{cert_pem_clean}
</ds:X509Certificate>
<ds:X509IssuerSerial>
<ds:X509IssuerName>{cert_issuer}</ds:X509IssuerName>
<ds:X509SerialNumber>{serial_number}</ds:X509SerialNumber>
</ds:X509IssuerSerial>
</ds:X509Data>
<ds:KeyValue>
<ds:RSAKeyValue>
<ds:Modulus>{modulus_b64}</ds:Modulus>
<ds:Exponent>{exponent_b64}</ds:Exponent>
</ds:RSAKeyValue>
</ds:KeyValue>
</ds:KeyInfo>'''

    prop_str = f'''<xades:SignedProperties Id="{SIGNED_PROPS_ID}"><xades:SignedSignatureProperties><xades:SigningTime>{sign_time}</xades:SigningTime><xades:SigningCertificate><xades:Cert><xades:CertDigest><ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/><ds:DigestValue>{cert_digest_sha1}</ds:DigestValue></xades:CertDigest><xades:IssuerSerial><ds:X509IssuerName>{cert_issuer}</ds:X509IssuerName><ds:X509SerialNumber>{serial_number}</ds:X509SerialNumber></xades:IssuerSerial></xades:Cert></xades:SigningCertificate><xades:SignaturePolicyIdentifier><xades:SignaturePolicyId><xades:SigPolicyId><xades:Identifier Qualifier="OIDAsURI">{POLITICA_URL}</xades:Identifier></xades:SigPolicyId><xades:SigPolicyHash><ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/><ds:DigestValue>{POLITICA_DIGEST_SHA1}</ds:DigestValue></xades:SigPolicyHash></xades:SignaturePolicyId></xades:SignaturePolicyIdentifier></xades:SignedSignatureProperties><xades:SignedDataObjectProperties><xades:DataObjectFormat ObjectReference="#{REF0_ID}"><xades:MimeType>text/xml</xades:MimeType><xades:Encoding>utf-8</xades:Encoding></xades:DataObjectFormat></xades:SignedDataObjectProperties></xades:SignedProperties>'''

    # ── 6. Insertar Signature temporal para calcular digests en contexto ───────
    sig_temp = f'''<ds:Signature xmlns:ds="{NS_DS}" Id="{SIG_ID}">
<ds:SignedInfo>PLACEHOLDER</ds:SignedInfo>
<ds:SignatureValue Id="{SIGVAL_ID}">PLACEHOLDER</ds:SignatureValue>
{k_info_str}
<ds:Object><xades:QualifyingProperties xmlns:xades="{NS_XADES}" xmlns:xades141="{NS_XADES141}" Target="#{SIG_ID}">{prop_str}</xades:QualifyingProperties></ds:Object>
</ds:Signature>'''

    xml_str = xml_sin_firma.decode("utf-8")
    xml_con_sig_temp = xml_str.replace(f"</{TAG_RAIZ}>", sig_temp + f"\n</{TAG_RAIZ}>")

    # ── 7. Calcular digests de KeyInfo y SignedProperties desde el documento ───
    doc_temp = etree.fromstring(xml_con_sig_temp.encode("utf-8"))

    keyinfo_node = doc_temp.find(f'.//{{{NS_DS}}}KeyInfo')
    props_node   = doc_temp.find(f'.//{{{NS_XADES}}}SignedProperties')

    # C14N explícito (como especifican los Transforms)
    kinfo_c14n   = _c14n_node(keyinfo_node)
    prop_c14n    = _c14n_node(props_node)

    kinfo_digest = _sha256_b64(kinfo_c14n)
    prop_digest  = _sha256_b64(prop_c14n)

    # ── 8. SignedInfo con transforms explícitos ───────────────────────────────
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
<ds:Reference URI="#{KEYINFO_ID}">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{kinfo_digest}</ds:DigestValue>
</ds:Reference>
<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#{SIGNED_PROPS_ID}">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{prop_digest}</ds:DigestValue>
</ds:Reference>
</ds:SignedInfo>'''

    signed_info_c14n = _c14n_fragment(signed_info_str)

    # ── 9. Firma RSA-SHA256 ───────────────────────────────────────────────────
    firma_bytes = private_key.sign(signed_info_c14n, padding.PKCS1v15(), hashes.SHA256())
    firma_b64   = base64.b64encode(firma_bytes).decode()

    # Partir la firma en líneas de 76 chars (como hace el XML de PMT)
    firma_lines = "\n".join([firma_b64[i:i+76] for i in range(0, len(firma_b64), 76)])

    # ── 10. SignedInfo sin namespaces extra (heredará del contexto) ───────────
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
<ds:Reference URI="#{KEYINFO_ID}">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{kinfo_digest}</ds:DigestValue>
</ds:Reference>
<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#{SIGNED_PROPS_ID}">
<ds:Transforms>
<ds:Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
</ds:Transforms>
<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<ds:DigestValue>{prop_digest}</ds:DigestValue>
</ds:Reference>
</ds:SignedInfo>'''

    # ── 11. Bloque Signature final ────────────────────────────────────────────
    sig_final = f'''<ds:Signature xmlns:ds="{NS_DS}" Id="{SIG_ID}">
{signed_info_inner}
<ds:SignatureValue Id="{SIGVAL_ID}">
{firma_lines}
</ds:SignatureValue>
{k_info_str}
<ds:Object><xades:QualifyingProperties xmlns:xades="{NS_XADES}" xmlns:xades141="{NS_XADES141}" Target="#{SIG_ID}">{prop_str}</xades:QualifyingProperties></ds:Object>
</ds:Signature>'''

    xml_firmado = xml_str.replace(f"</{TAG_RAIZ}>", sig_final + f"\n</{TAG_RAIZ}>")
    return xml_firmado.encode("utf-8")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '/home/claude/facturador_cr')
    from xml_generator import generar_xml

    xml = generar_xml(
        clave="50605062600310280744200100001040000000099887766554",
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

    xf = firmar('/mnt/user-data/uploads/certificado1__1_.p12', '5561', xml, '04')
    print(f"✅ XML firmado: {len(xf)} bytes")
    print(xf.decode()[-500:])
