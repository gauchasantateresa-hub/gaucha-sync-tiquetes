"""
Firmador XAdES-EPES para Hacienda CR v4.4
Basado en tiquete electrónico ACEPTADO de Armonia/TipsCR (jun 2026)
"""
import base64, hashlib
from datetime import datetime
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

# URL de política — v4.3 (la que usa el tiquete aceptado)
POLITICA_URL = "https://www.hacienda.go.cr/ATV/ComprobanteElectronico/docs/esquemas/2016/v4.3/ResolucionComprobantesElectronicosDGT-R-48-2016_4.3.pdf"
# Digest SHA256 de la política (base64 del hash del PDF)
POLITICA_DIGEST = "NmI5Njk1ZThkNzI0MmIzMGJmZDAyNDc4YjUwNzkzODM2NTBiOWUxNTBkMmI2YjgzYzZjM2I5NTZlNDQ4OWQzMQ=="

NODOS_NS = {
    "01": "facturaElectronica",    "02": "notaDebitoElectronica",
    "03": "notaCreditoElectronica","04": "tiqueteElectronico",
    "05": "mensajeReceptor",       "06": "mensajeReceptor",
    "07": "mensajeReceptor",
}
NS_BASE  = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/"
NS_DS    = "http://www.w3.org/2000/09/xmldsig#"
NS_XSI   = "http://www.w3.org/2001/XMLSchema-instance"
NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"

import uuid
def _uid(): return str(uuid.uuid4())

def _c14n(node) -> bytes:
    return etree.tostring(node, method="c14n")

def _sha256_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()

def _oid_name(oid):
    nombres = {
        "2.5.4.3":"CN","2.5.4.6":"C","2.5.4.7":"L","2.5.4.8":"ST",
        "2.5.4.10":"O","2.5.4.11":"OU","2.5.4.5":"serialNumber",
    }
    return nombres.get(oid.dotted_string, oid.dotted_string)


def firmar(p12_path: str, pin: str, xml_sin_firma: bytes, tipo_doc: str = "04") -> bytes:
    # ── 1. Certificado ────────────────────────────────────────────────────────
    with open(p12_path, "rb") as f:
        p12_data = f.read()
    private_key, cert, _ = pkcs12.load_key_and_certificates(p12_data, pin.encode())

    cert_der = cert.public_bytes(Encoding.DER)
    cert_pem = cert.public_bytes(Encoding.PEM).decode()
    cert_pem_clean = (cert_pem
        .replace("-----BEGIN CERTIFICATE-----","")
        .replace("-----END CERTIFICATE-----","")
        .replace("\n","").replace("\r","").strip())

    # SHA256 del certificado (como usa el tiquete aceptado)
    cert_digest_sha256 = _sha256_b64(cert_der)

    # Issuer en formato "CN=..., OU=..., O=..., C=CR"
    issuer_parts = []
    for attr in reversed(list(cert.issuer)):
        issuer_parts.append(f"{_oid_name(attr.oid)}={attr.value}")
    cert_issuer = ", ".join(issuer_parts)
    serial_number = str(cert.serial_number)

    # RSA key
    pub = private_key.public_key().public_numbers()
    modulus_b64  = base64.b64encode(pub.n.to_bytes((pub.n.bit_length()+7)//8,"big")).decode()
    exponent_b64 = base64.b64encode(pub.e.to_bytes((pub.e.bit_length()+7)//8,"big")).decode()

    # ── 2. IDs únicos ─────────────────────────────────────────────────────────
    sig_id        = f"Signature-{_uid()}"
    keyinfo_id    = f"KeyInfoId-{sig_id}"
    ref0_id       = f"Reference-{_uid()}"
    sigval_id     = f"SignatureValue-{sig_id}"
    signedprops_id= f"SignedProperties-{sig_id}"
    xobj_id       = f"XadesObjectId-{_uid()}"
    qprops_id     = f"QualifyingProperties-{_uid()}"

    # ── 3. Namespace y tag raíz ───────────────────────────────────────────────
    NS_DOC = NS_BASE + NODOS_NS.get(tipo_doc, "tiqueteElectronico")
    TAG_RAIZ = {
        "01":"FacturaElectronica","02":"NotaDebitoElectronica",
        "03":"NotaCreditoElectronica","04":"TiqueteElectronico",
    }.get(tipo_doc, "TiqueteElectronico")

    # ── 4. Digest del documento ───────────────────────────────────────────────
    doc_orig  = etree.fromstring(xml_sin_firma)
    doc_digest = _sha256_b64(_c14n(doc_orig))

    # ── 5. Tiempo ─────────────────────────────────────────────────────────────
    sign_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00")

    # ── 6. KeyInfo y SignedProperties como strings ────────────────────────────
    k_info_str = f'<ds:KeyInfo Id="{keyinfo_id}"><ds:X509Data><ds:X509Certificate>{cert_pem_clean}</ds:X509Certificate></ds:X509Data><ds:KeyValue><ds:RSAKeyValue><ds:Modulus>{modulus_b64}</ds:Modulus><ds:Exponent>{exponent_b64}</ds:Exponent></ds:RSAKeyValue></ds:KeyValue></ds:KeyInfo>'

    prop_str = (
        f'<xades:SignedProperties Id="{signedprops_id}">'
        f'<xades:SignedSignatureProperties>'
        f'<xades:SigningTime>{sign_time}</xades:SigningTime>'
        f'<xades:SigningCertificate><xades:Cert><xades:CertDigest>'
        f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue>{cert_digest_sha256}</ds:DigestValue>'
        f'</xades:CertDigest><xades:IssuerSerial>'
        f'<ds:X509IssuerName>{cert_issuer}</ds:X509IssuerName>'
        f'<ds:X509SerialNumber>{serial_number}</ds:X509SerialNumber>'
        f'</xades:IssuerSerial></xades:Cert></xades:SigningCertificate>'
        f'<xades:SignaturePolicyIdentifier><xades:SignaturePolicyId><xades:SigPolicyId>'
        f'<xades:Identifier>{POLITICA_URL}</xades:Identifier>'
        f'<xades:Description /></xades:SigPolicyId>'
        f'<xades:SigPolicyHash>'
        f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue>{POLITICA_DIGEST}</ds:DigestValue>'
        f'</xades:SigPolicyHash></xades:SignaturePolicyId></xades:SignaturePolicyIdentifier>'
        f'<xades:SignerRole><xades:ClaimedRoles>'
        f'<xades:ClaimedRole>obligadotributario</xades:ClaimedRole>'
        f'</xades:ClaimedRoles></xades:SignerRole>'
        f'</xades:SignedSignatureProperties>'
        f'<xades:SignedDataObjectProperties>'
        f'<xades:DataObjectFormat ObjectReference="#{ref0_id}">'
        f'<xades:MimeType>text/xml</xades:MimeType>'
        f'<xades:Encoding>UTF-8</xades:Encoding>'
        f'</xades:DataObjectFormat></xades:SignedDataObjectProperties>'
        f'</xades:SignedProperties>'
    )

    # ── 7. Insertar Signature temporal para calcular digests en contexto ──────
    sig_temp = (
        f'<ds:Signature xmlns:ds="{NS_DS}" Id="{sig_id}">'
        f'<ds:SignedInfo>PLACEHOLDER</ds:SignedInfo>'
        f'<ds:SignatureValue Id="{sigval_id}">PLACEHOLDER</ds:SignatureValue>'
        f'{k_info_str}'
        f'<ds:Object Id="{xobj_id}">'
        f'<xades:QualifyingProperties xmlns:xades="{NS_XADES}" Id="{qprops_id}" Target="#{sig_id}">'
        f'{prop_str}'
        f'</xades:QualifyingProperties></ds:Object>'
        f'</ds:Signature>'
    )

    xml_str = xml_sin_firma.decode("utf-8")
    xml_temp = xml_str.replace(f"</{TAG_RAIZ}>", sig_temp + f"\n</{TAG_RAIZ}>")

    # ── 8. Calcular digests desde el documento ensamblado ─────────────────────
    doc_temp = etree.fromstring(xml_temp.encode("utf-8"))

    keyinfo_node = doc_temp.find(f'.//{{{NS_DS}}}KeyInfo')
    props_node   = doc_temp.find(f'.//{{{NS_XADES}}}SignedProperties')

    kinfo_digest = _sha256_b64(_c14n(keyinfo_node))
    prop_digest  = _sha256_b64(_c14n(props_node))

    # ── 9. SignedInfo con los digests correctos ───────────────────────────────
    # SIN transforms en KeyInfo y SignedProperties (igual que el tiquete aceptado)
    signed_info_str = (
        f'<ds:SignedInfo xmlns:ds="{NS_DS}" xmlns="{NS_DOC}" xmlns:xsi="{NS_XSI}">'
        f'<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315" />'
        f'<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256" />'
        f'<ds:Reference Id="{ref0_id}" URI="">'
        f'<ds:Transforms><ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature" /></ds:Transforms>'
        f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue>{doc_digest}</ds:DigestValue>'
        f'</ds:Reference>'
        f'<ds:Reference Id="ReferenceKeyInfo" URI="#{keyinfo_id}">'
        f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue>{kinfo_digest}</ds:DigestValue>'
        f'</ds:Reference>'
        f'<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#{signedprops_id}">'
        f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue>{prop_digest}</ds:DigestValue>'
        f'</ds:Reference>'
        f'</ds:SignedInfo>'
    )

    # C14N del SignedInfo para firmar
    signed_info_c14n = etree.tostring(etree.fromstring(signed_info_str.encode()), method="c14n")

    # ── 10. Firma RSA-SHA256 ──────────────────────────────────────────────────
    firma_bytes = private_key.sign(signed_info_c14n, padding.PKCS1v15(), hashes.SHA256())
    firma_b64   = base64.b64encode(firma_bytes).decode()

    # ── 11. SignedInfo final (sin namespaces extra, hereda del contexto) ───────
    signed_info_inner = (
        f'<ds:SignedInfo>'
        f'<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315" />'
        f'<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256" />'
        f'<ds:Reference Id="{ref0_id}" URI="">'
        f'<ds:Transforms><ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature" /></ds:Transforms>'
        f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue>{doc_digest}</ds:DigestValue>'
        f'</ds:Reference>'
        f'<ds:Reference Id="ReferenceKeyInfo" URI="#{keyinfo_id}">'
        f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue>{kinfo_digest}</ds:DigestValue>'
        f'</ds:Reference>'
        f'<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#{signedprops_id}">'
        f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue>{prop_digest}</ds:DigestValue>'
        f'</ds:Reference>'
        f'</ds:SignedInfo>'
    )

    # ── 12. Bloque Signature final ────────────────────────────────────────────
    sig_final = (
        f'<ds:Signature xmlns:ds="{NS_DS}" Id="{sig_id}">'
        f'{signed_info_inner}'
        f'<ds:SignatureValue Id="{sigval_id}">{firma_b64}</ds:SignatureValue>'
        f'{k_info_str}'
        f'<ds:Object Id="{xobj_id}">'
        f'<xades:QualifyingProperties xmlns:xades="{NS_XADES}" Id="{qprops_id}" Target="#{sig_id}">'
        f'{prop_str}'
        f'</xades:QualifyingProperties></ds:Object>'
        f'</ds:Signature>'
    )

    xml_firmado = xml_str.replace(f"</{TAG_RAIZ}>", sig_final + f"\n</{TAG_RAIZ}>")
    return xml_firmado.encode("utf-8")
