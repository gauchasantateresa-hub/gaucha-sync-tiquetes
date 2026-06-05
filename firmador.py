"""
Firmador XAdES-EPES para Hacienda CR v4.4
Estructura validada contra tiquete aceptado de Armonia (jun 2026)
"""
import hashlib, base64, uuid
from datetime import datetime
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

NS_DOC   = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico"
NS_DS    = "http://www.w3.org/2000/09/xmldsig#"
NS_XSI   = "http://www.w3.org/2001/XMLSchema-instance"
NS_XADES = "http://uri.etsi.org/01903/v1.3.2#"

# URL política v4.3 + SigPolicyHash exacto (base64 de string hex del SHA256 del PDF)
POLITICA_URL  = "https://www.hacienda.go.cr/ATV/ComprobanteElectronico/docs/esquemas/2016/v4.3/ResolucionComprobantesElectronicosDGT-R-48-2016_4.3.pdf"
POLITICA_HASH = "NmI5Njk1ZThkNzI0MmIzMGJmZDAyNDc4YjUwNzkzODM2NTBiOWUxNTBkMmI2YjgzYzZjM2I5NTZlNDQ4OWQzMQ=="


def firmar(p12_path: str, pin: str, xml_bytes: bytes, tipo_doc: str = "04") -> bytes:
    # ── Certificado ───────────────────────────────────────────────────────────
    with open(p12_path, 'rb') as f:
        p12_data = f.read()
    private_key, cert, _ = pkcs12.load_key_and_certificates(p12_data, pin.encode())

    cert_der = cert.public_bytes(Encoding.DER)
    cert_pem = cert.public_bytes(Encoding.PEM).decode()
    cert_pem_clean = (cert_pem
        .replace("-----BEGIN CERTIFICATE-----", "")
        .replace("-----END CERTIFICATE-----", "")
        .replace("\n", "").replace("\r", "").strip())

    cert_digest = base64.b64encode(hashlib.sha256(cert_der).digest()).decode()

    # Issuer DN en formato Armonia: "CN=..., OU=..., O=..., C=..."
    im = {}
    for a in cert.issuer:
        s = {"2.5.4.3":"CN","2.5.4.6":"C","2.5.4.10":"O","2.5.4.11":"OU"}.get(a.oid.dotted_string, a.oid.dotted_string)
        im[s] = a.value
    issuer_dn = f"CN={im.get('CN','')}, OU={im.get('OU','')}, O={im.get('O','')}, C={im.get('C','')}"
    serial    = str(cert.serial_number)

    pub = private_key.public_key().public_numbers()
    mod_b64 = base64.b64encode(pub.n.to_bytes((pub.n.bit_length()+7)//8,"big")).decode()
    exp_b64 = base64.b64encode(pub.e.to_bytes((pub.e.bit_length()+7)//8,"big")).decode()

    # ── IDs ───────────────────────────────────────────────────────────────────
    sig_id = f"Signature-{uuid.uuid4()}"
    ref_id = f"Reference-{uuid.uuid4()}"
    ki_id  = f"KeyInfoId-{sig_id}"
    sp_id  = f"SignedProperties-{sig_id}"
    xo_id  = f"XadesObjectId-{uuid.uuid4()}"
    qp_id  = f"QualifyingProperties-{uuid.uuid4()}"

    sign_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00")

    # ── Digest del documento ──────────────────────────────────────────────────
    doc_orig   = etree.fromstring(xml_bytes)
    doc_digest = base64.b64encode(
        hashlib.sha256(etree.tostring(doc_orig, method="c14n")).digest()
    ).decode()

    # ── SignedProperties ──────────────────────────────────────────────────────
    sp = (
        f'<xades:SignedProperties xmlns:xades="{NS_XADES}" Id="{sp_id}">'
        f'<xades:SignedSignatureProperties>'
        f'<xades:SigningTime>{sign_time}</xades:SigningTime>'
        f'<xades:SigningCertificate><xades:Cert><xades:CertDigest>'
        f'<ds:DigestMethod xmlns:ds="{NS_DS}" Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue xmlns:ds="{NS_DS}">{cert_digest}</ds:DigestValue>'
        f'</xades:CertDigest><xades:IssuerSerial>'
        f'<ds:X509IssuerName xmlns:ds="{NS_DS}">{issuer_dn}</ds:X509IssuerName>'
        f'<ds:X509SerialNumber xmlns:ds="{NS_DS}">{serial}</ds:X509SerialNumber>'
        f'</xades:IssuerSerial></xades:Cert></xades:SigningCertificate>'
        f'<xades:SignaturePolicyIdentifier><xades:SignaturePolicyId><xades:SigPolicyId>'
        f'<xades:Identifier>{POLITICA_URL}</xades:Identifier>'
        f'<xades:Description /></xades:SigPolicyId>'
        f'<xades:SigPolicyHash>'
        f'<ds:DigestMethod xmlns:ds="{NS_DS}" Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" />'
        f'<ds:DigestValue xmlns:ds="{NS_DS}">{POLITICA_HASH}</ds:DigestValue>'
        f'</xades:SigPolicyHash></xades:SignaturePolicyId></xades:SignaturePolicyIdentifier>'
        f'<xades:SignerRole><xades:ClaimedRoles>'
        f'<xades:ClaimedRole>obligadotributario</xades:ClaimedRole>'
        f'</xades:ClaimedRoles></xades:SignerRole>'
        f'</xades:SignedSignatureProperties>'
        f'<xades:SignedDataObjectProperties>'
        f'<xades:DataObjectFormat ObjectReference="#{ref_id}">'
        f'<xades:MimeType>text/xml</xades:MimeType>'
        f'<xades:Encoding>UTF-8</xades:Encoding>'
        f'</xades:DataObjectFormat>'
        f'</xades:SignedDataObjectProperties>'
        f'</xades:SignedProperties>'
    )

    # ── KeyInfo ───────────────────────────────────────────────────────────────
    ki = (
        f'<ds:KeyInfo xmlns:ds="{NS_DS}" Id="{ki_id}">'
        f'<ds:X509Data><ds:X509Certificate>{cert_pem_clean}</ds:X509Certificate></ds:X509Data>'
        f'<ds:KeyValue><ds:RSAKeyValue>'
        f'<ds:Modulus>{mod_b64}</ds:Modulus>'
        f'<ds:Exponent>{exp_b64}</ds:Exponent>'
        f'</ds:RSAKeyValue></ds:KeyValue>'
        f'</ds:KeyInfo>'
    )

    # ── Calcular digests de KeyInfo y SignedProperties en contexto ─────────────
    xml_str  = xml_bytes.decode('utf-8')
    xml_temp = xml_str.replace(
        '</TiqueteElectronico>',
        f'<ds:Signature xmlns:ds="{NS_DS}" Id="{sig_id}">'
        f'<ds:SignedInfo>PH</ds:SignedInfo>'
        f'<ds:SignatureValue>PH</ds:SignatureValue>'
        f'{ki}'
        f'<ds:Object Id="{xo_id}">'
        f'<xades:QualifyingProperties xmlns:xades="{NS_XADES}" Id="{qp_id}" Target="#{sig_id}">'
        f'{sp}</xades:QualifyingProperties></ds:Object>'
        f'</ds:Signature></TiqueteElectronico>'
    )
    doc_t  = etree.fromstring(xml_temp.encode())
    ki_node = doc_t.find(f'.//{{{NS_DS}}}KeyInfo')
    sp_node = doc_t.find(f'.//{{{NS_XADES}}}SignedProperties')
    ki_dig  = base64.b64encode(hashlib.sha256(etree.tostring(ki_node, method="c14n")).digest()).decode()
    sp_dig  = base64.b64encode(hashlib.sha256(etree.tostring(sp_node, method="c14n")).digest()).decode()

    # ── SignedInfo ────────────────────────────────────────────────────────────
    def si_xml(with_ns):
        ns = f' xmlns:ds="{NS_DS}" xmlns="{NS_DOC}" xmlns:xsi="{NS_XSI}"' if with_ns else ""
        return (
            f'<ds:SignedInfo{ns}>'
            f'<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
            f'<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>'
            f'<ds:Reference Id="{ref_id}" URI="">'
            f'<ds:Transforms><ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/></ds:Transforms>'
            f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>'
            f'<ds:DigestValue>{doc_digest}</ds:DigestValue>'
            f'</ds:Reference>'
            f'<ds:Reference URI="#{ki_id}">'
            f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>'
            f'<ds:DigestValue>{ki_dig}</ds:DigestValue>'
            f'</ds:Reference>'
            f'<ds:Reference Type="http://uri.etsi.org/01903#SignedProperties" URI="#{sp_id}">'
            f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>'
            f'<ds:DigestValue>{sp_dig}</ds:DigestValue>'
            f'</ds:Reference>'
            f'</ds:SignedInfo>'
        )

    si_c14n     = etree.tostring(etree.fromstring(si_xml(True).encode()), method="c14n")
    firma_bytes = private_key.sign(si_c14n, padding.PKCS1v15(), hashes.SHA256())
    firma_b64   = base64.b64encode(firma_bytes).decode()

    sig_final = (
        f'<ds:Signature xmlns:ds="{NS_DS}" Id="{sig_id}">'
        f'{si_xml(False)}'
        f'<ds:SignatureValue>{firma_b64}</ds:SignatureValue>'
        f'{ki}'
        f'<ds:Object Id="{xo_id}">'
        f'<xades:QualifyingProperties xmlns:xades="{NS_XADES}" Id="{qp_id}" Target="#{sig_id}">'
        f'{sp}</xades:QualifyingProperties></ds:Object>'
        f'</ds:Signature>'
    )

    return xml_str.replace('</TiqueteElectronico>', sig_final + '</TiqueteElectronico>').encode('utf-8')
