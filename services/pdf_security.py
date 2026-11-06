"""Export an unlocked PDF copy without modifying the signed source bytes."""
from io import BytesIO
from pypdf import PdfReader, PdfWriter


def unlocked_copy(payload: bytes, password: str) -> bytes:
    reader = PdfReader(BytesIO(payload))
    if reader.is_encrypted and not reader.decrypt(password):
        raise ValueError("Password errata. Riapri il PDF e riprova.")
    writer = PdfWriter(clone_from=reader)
    output = BytesIO()
    writer.write(output)
    result = output.getvalue()
    check = PdfReader(BytesIO(result))
    if check.is_encrypted or len(check.pages) != len(reader.pages):
        raise ValueError("La copia senza password non ha superato la verifica.")
    return result
