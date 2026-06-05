"""
Firmador XAdES-EPES para Hacienda CR v4.4
Usa xmlsig + xades — librerías que manejan la firma correctamente
Basado en: https://github.com/open-byte/xml-signer
"""
import warnings
warnings.filterwarnings('ignore')

from lxml import etree
from OpenSSL import crypto
from xades import XAdESContext, template
from uuid import uuid4
import xmlsig


def firmar(p12_path: str, pin: str, xml_sin_firma: bytes, tipo_doc: str = "04") -> bytes:
    """
    Firma el XML con XAdES-EPES usando xmlsig + xades.
    Retorna bytes del XML firmado.
    """
    parsed_file = etree.fromstring(xml_sin_firma)

    signature_id = f'Signature-{str(uuid4())}'
    reference_id = f'Reference-{str(uuid4())}'

    # Crear template de firma
    signature = xmlsig.template.create(
        xmlsig.constants.TransformInclC14N,
        xmlsig.constants.TransformRsaSha256,
        signature_id,
    )

    # Reference al documento (con enveloped transform)
    ref = xmlsig.template.add_reference(
        signature,
        xmlsig.constants.TransformSha256,
        uri="",
        name=reference_id
    )
    xmlsig.template.add_transform(ref, xmlsig.constants.TransformEnveloped)

    # Reference al KeyInfo
    xmlsig.template.add_reference(
        signature,
        xmlsig.constants.TransformSha256,
        uri=f"#KeyInfoId-{signature_id}",
        name="ReferenceKeyInfo"
    )

    # Reference a SignedProperties
    xmlsig.template.add_reference(
        signature,
        xmlsig.constants.TransformSha256,
        uri=f"#SignedProperties-{signature_id}",
        uri_type="http://uri.etsi.org/01903#SignedProperties",
    )

    # KeyInfo con certificado
    key = xmlsig.template.ensure_key_info(signature, name=f"KeyInfoId-{signature_id}")
    x509_data = xmlsig.template.add_x509_data(key)
    xmlsig.template.x509_data_add_certificate(x509_data)
    xmlsig.template.add_key_value(key)

    # XAdES QualifyingProperties
    qualifying = template.create_qualifying_properties(
        signature,
        name=f"Qualifying-Properties-{signature_id}",
        etsi='xades'
    )
    props = template.create_signed_properties(
        qualifying,
        name=f'SignedProperties-{signature_id}'
    )
    template.add_production_place(props)

    # Insertar firma en el documento
    parsed_file.append(signature)

    # Cargar certificado y firmar
    with open(p12_path, 'rb') as f:
        p12_data = f.read()

    cryto_certificate = crypto.load_pkcs12(p12_data, pin.encode('utf-8'))
    ctx = XAdESContext(
        None,
        (cryto_certificate.get_certificate().to_cryptography(),)
    )
    ctx.load_pkcs12(cryto_certificate)
    ctx.sign(signature)

    # Serializar
    xml_firmado = etree.tostring(etree.ElementTree(parsed_file))
    return xml_firmado
