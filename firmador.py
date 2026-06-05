"""
Módulo 3: Firmador XAdES-EPES para Hacienda CR v4.4
Traducción fiel del PHP Firmadohaciendacr.php de CRLibre
"""
import base64
import hashlib
from datetime import datetime
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, NoEncryption
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID
import cryptography.x509 as x509


POLITICA_URL    = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/Resoluci%C3%B3n_General_sobre_disposiciones_t%C3%A9cnicas_comprobantes_electr%C3%B3nicos_para_efectos_tributarios.pdf"
POLITICA_DIGEST = "DWxin1xWOeI8OuWQXazh4VjLWAaCLAA954em7DMh0h8="

NODOS_NS = {
    "01": "facturaElectronica",
    "02": "notaDebitoElectronica",
    "03": "notaCreditoElectronica",
    "04": "tiqueteElectronico",
    "05": "mensajeReceptor",
    "06": "mensajeReceptor",
    "07": "mensajeReceptor",
}
NS_BASE = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/"

SIG_ID   = "Signature-ddb543c7-ea0c-4b00-95b9-d4bfa2b4e411"
SIG_VAL  = "SignatureValue-ddb543c7-ea0c-4b00-95b9-d4bfa2b4e411"
XOBJ_ID  = "XadesObjectId-43208d10-650c-4f42-af80-fc889962c9ac"
KEYINFO_ID  = f"KeyInfoId-{SIG_ID}"
REF0_ID  = "Reference-0e79b719-635c-476f-a59e-8ac3ba14365d"
REF1_ID  = "ReferenceKeyInfo"
SIGNED_PROPS_ID = f"SignedProperties-{SIG_ID}"


def _c14n_digest(xml_str: str) -> str:
    """C14N del fragmento XML y SHA-256 en base64."""
    doc = etree.fromstring(xml_str.encode("utf-8"))
    c14n = etree.tostring(doc, method="c14n")
    digest = hashlib.sha256(c14n).digest()
    return base64.b64encode(digest).decode()


def _c14n_bytes(xml_str: str) -> bytes:
    doc = etree.fromstring(xml_str.encode("utf-8"))
    return etree.tostring(doc, method="c14n")


def firmar(p12_path: str, pin: str, xml_sin_firma: bytes, tipo_doc: str = "04") -> bytes:
    """
    Firma el XML con XAdES-EPES usando el certificado .p12 de Hacienda CR.
    
    Args:
        p12_path: ruta al archivo .p12
        pin: contraseña del certificado
        xml_sin_firma: XML en bytes (sin firma)
        tipo_doc: "04" para tiquete electrónico
    
    Returns:
        XML firmado en bytes
    """
    # ── 1. Leer certificado ───────────────────────────────────────────────────
    with open(p12_path, "rb") as f:
        p12_data = f.read()

    private_key, cert, chain = pkcs12.load_key_and_certificates(
        p12_data, pin.encode("utf-8")
    )

    # Exportar clave pública como PEM limpio (sin headers)
    cert_pem = cert.public_bytes(Encoding.PEM).decode()
    cert_pem_clean = cert_pem.replace("-----BEGIN CERTIFICATE-----", "") \
                              .replace("-----END CERTIFICATE-----", "") \
                              .replace("\n", "").replace("\r", "").strip()

    # Digest del certificado (SHA-256)
    cert_der = cert.public_bytes(Encoding.DER)
    cert_digest = base64.b64encode(hashlib.sha256(cert_der).digest()).decode()

    # Issuer en formato DN invertido
    issuer_parts = []
    for attr in reversed(list(cert.issuer)):
        issuer_parts.append(f"{attr.oid.dotted_string}={attr.value}" if len(attr.oid.dotted_string) > 4 
                           else f"{_oid_name(attr.oid)}={attr.value}")
    cert_issuer = ", ".join(issuer_parts)
    
    # Serial number
    serial_number = str(cert.serial_number)

    # Módulo y exponente RSA
    pub_numbers = private_key.public_key().public_key().public_numbers() \
        if hasattr(private_key.public_key(), 'public_key') \
        else private_key.public_key().public_numbers()
    
    modulus_b64   = base64.b64encode(pub_numbers.n.to_bytes((pub_numbers.n.bit_length() + 7) // 8, "big")).decode()
    exponent_b64  = base64.b64encode(pub_numbers.e.to_bytes((pub_numbers.e.bit_length() + 7) // 8, "big")).decode()

    # ── 2. Namespace del tipo de documento ───────────────────────────────────
    doc_ns = NS_BASE + NODOS_NS.get(tipo_doc, "tiqueteElectronico")
    xmlns_base = f'xmlns="{doc_ns}" '

    xmlns_keyinfo = xmlns_base + \
        'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" ' + \
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" ' + \
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'

    xmlns_signedprops = xmlns_base + \
        'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" ' + \
        'xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" ' + \
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" ' + \
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'

    xmlns_signedinfo = xmlns_base + \
        'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" ' + \
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" ' + \
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'

    # ── 3. Tiempo de firma ────────────────────────────────────────────────────
    sign_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00")

    # ── 4. SignedProperties ───────────────────────────────────────────────────
    prop = f'''<xades:SignedProperties Id="{SIGNED_PROPS_ID}">
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

    # ── 5. KeyInfo ────────────────────────────────────────────────────────────
    k_info = f'''<ds:KeyInfo Id="{KEYINFO_ID}">
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

    # ── 6. Digests ────────────────────────────────────────────────────────────
    # Digest del documento original (C14N del XML completo)
    doc = etree.fromstring(xml_sin_firma)
    doc_c14n = etree.tostring(doc, method="c14n")
    doc_digest = base64.b64encode(hashlib.sha256(doc_c14n).digest()).decode()

    # Digest de SignedProperties (con namespace)
    prop_con_ns = prop.replace("<xades:SignedProperties", f"<xades:SignedProperties {xmlns_signedprops}")
    prop_digest = _c14n_digest(prop_con_ns)

    # Digest de KeyInfo (con namespace)
    kinfo_con_ns = k_info.replace("<ds:KeyInfo", f"<ds:KeyInfo {xmlns_keyinfo}")
    kinfo_digest = _c14n_digest(kinfo_con_ns)

    # ── 7. SignedInfo ─────────────────────────────────────────────────────────
    signed_info = f'''<ds:SignedInfo>
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
    signed_info_con_ns = signed_info.replace("<ds:SignedInfo", f"<ds:SignedInfo {xmlns_signedinfo}")
    signed_info_c14n = _c14n_bytes(signed_info_con_ns)

    # ── 8. Firma RSA-SHA256 ───────────────────────────────────────────────────
    firma_bytes = private_key.sign(signed_info_c14n, padding.PKCS1v15(), hashes.SHA256())
    firma_b64   = base64.b64encode(firma_bytes).decode()

    # ── 9. Armar bloque Signature completo ───────────────────────────────────
    signature_block = f'''<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="{SIG_ID}">
{signed_info}
<ds:SignatureValue Id="{SIG_VAL}">{firma_b64}</ds:SignatureValue>
{k_info}
<ds:Object Id="{XOBJ_ID}">
<xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Target="#{SIG_ID}">
{prop}
</xades:QualifyingProperties>
</ds:Object>
</ds:Signature>'''

    # ── 10. Insertar firma en el XML ──────────────────────────────────────────
    xml_str = xml_sin_firma.decode("utf-8")
    
    # Encontrar el tag de cierre raíz e insertar antes
    tag_raiz = "TiqueteElectronico"
    cierre = f"</{tag_raiz}>"
    xml_firmado = xml_str.replace(cierre, signature_block + "\n" + cierre)

    return xml_firmado.encode("utf-8")


def _oid_name(oid):
    """Convierte OID a nombre corto estándar."""
    nombres = {
        "2.5.4.3":  "CN",
        "2.5.4.6":  "C",
        "2.5.4.7":  "L",
        "2.5.4.8":  "ST",
        "2.5.4.10": "O",
        "2.5.4.11": "OU",
        "1.2.840.113549.1.9.1": "emailAddress",
        "2.5.4.5":  "serialNumber",
    }
    return nombres.get(oid.dotted_string, oid.dotted_string)


if __name__ == "__main__":
    import sys, os
    p12 = "/mnt/user-data/uploads/certificado1__1_.p12"
    if not os.path.exists(p12):
        print("❌ No se encuentra el certificado en:", p12)
        sys.exit(1)

    # XML de prueba mínimo
    xml_test = b"""<?xml version='1.0' encoding='UTF-8'?>
<TiqueteElectronico xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico">
<Clave>50605062600310280744200100001040000000001164227489</Clave>
</TiqueteElectronico>"""

    try:
        xml_firmado = firmar(p12, "5561", xml_test, "04")
        print("✅ XML firmado correctamente!")
        print(f"   Tamaño: {len(xml_firmado)} bytes")
        print("   Primeros 500 chars:")
        print(xml_firmado.decode()[:500])
    except Exception as e:
        import traceback
        print("❌ Error:", e)
        traceback.print_exc()
