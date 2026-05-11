from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["legal"])

_DATA_DELETION_HTML = """<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Eliminación de datos — Tienda Mágica</title></head>
<body>
<h1>Eliminación de datos de usuario</h1>
<p>Para solicitar la eliminación de tus datos personales asociados a Tienda Mágica,
envía un correo a: <a href="mailto:josseph_14@hotmail.com">josseph_14@hotmail.com</a></p>
<p>Tu solicitud será procesada en un plazo máximo de 30 días.</p>
</body>
</html>"""


@router.get("/data-deletion", response_class=HTMLResponse, include_in_schema=False)
async def data_deletion() -> HTMLResponse:
    return HTMLResponse(content=_DATA_DELETION_HTML)
