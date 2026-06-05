"""
Módulo 1: Generador de clave numérica de 50 dígitos
Hacienda CR v4.4
"""
import random
from datetime import datetime

def generar_consecutivo(numero: int, tipo_doc: str = "04",
                         sucursal: str = "001", terminal: str = "00001") -> str:
    """
    Consecutivo = sucursal(3) + terminal(5) + tipo_doc(2) + numero(10) = 20 dígitos
    """
    tipos = {
        "FE": "01", "ND": "02", "NC": "03", "TE": "04",
        "CCE": "05", "CPCE": "06", "RCE": "07", "FEC": "08", "FEE": "09"
    }
    cod_tipo = tipos.get(tipo_doc, tipo_doc)  # acepta también "01","04", etc.
    num_str = str(numero).zfill(10)
    return f"{sucursal}{terminal}{cod_tipo}{num_str}"

def generar_clave(cedula: str, consecutivo_num: int, tipo_cedula: str = "02",
                  tipo_doc: str = "04", fecha: datetime = None,
                  situacion: str = "normal", sucursal: str = "001",
                  terminal: str = "00001", codigo_pais: str = "506") -> dict:
    """
    Genera la clave de 50 dígitos que exige Hacienda.
    
    Formato:
    codigoPais(3) + dia(2) + mes(2) + año(2) + cedula(12) +
    consecutivo(20) + situacion(1) + codigoSeguridad(8) = 50 dígitos
    """
    if fecha is None:
        fecha = datetime.now()

    # Identificación — cédula jurídica = 12 dígitos con ceros a la izquierda
    tipos_cedula = {"fisico": "01", "juridico": "02", "dimex": "03", "nite": "04"}
    # Si ya viene como "02" lo usamos directo
    if tipo_cedula in tipos_cedula:
        tipo_cedula = tipos_cedula[tipo_cedula]

    # Rellenar cédula a 12 dígitos
    cedula_limpia = cedula.replace("-", "").replace(" ", "")
    if tipo_cedula == "02":  # jurídica
        identificacion = cedula_limpia.zfill(12)
    else:
        identificacion = cedula_limpia.zfill(12)

    # Consecutivo 20 dígitos
    consecutivo_str = generar_consecutivo(consecutivo_num, tipo_doc, sucursal, terminal)

    # Situación
    situaciones = {"normal": "1", "contingencia": "2", "sininternet": "3"}
    cod_situacion = situaciones.get(situacion.lower(), "1")

    # Código de seguridad: 8 dígitos aleatorios
    codigo_seguridad = str(random.randint(10000000, 99999999))

    # Fecha
    dia = fecha.strftime("%d")
    mes = fecha.strftime("%m")
    ano = fecha.strftime("%y")  # 2 dígitos

    # Armar clave
    clave = f"{codigo_pais}{dia}{mes}{ano}{identificacion}{consecutivo_str}{cod_situacion}{codigo_seguridad}"

    assert len(clave) == 50, f"Clave debe tener 50 dígitos, tiene {len(clave)}: {clave}"

    return {
        "clave": clave,
        "consecutivo": consecutivo_str,
        "codigo_seguridad": codigo_seguridad,
        "longitud": len(clave)
    }


if __name__ == "__main__":
    from datetime import datetime
    resultado = generar_clave(
        cedula="3102807442",
        consecutivo_num=1,
        tipo_cedula="02",
        tipo_doc="04",
        fecha=datetime(2026, 6, 5)
    )
    print("✅ Clave generada:")
    for k, v in resultado.items():
        print(f"  {k}: {v}")
