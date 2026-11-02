"""Texto de las preguntas para el médico.

El agente a veces copia los nombres de los exámenes tal como los escribe el laboratorio
("RECUENTO DE GLOBULOS BLANCOS") y la pregunta queda gritando. Esto la deja en minúsculas
normales, con la primera letra en mayúscula, y conserva las siglas."""

import re

ACRONYMS = {
    "ldl", "hdl", "vldl", "psa", "tsh", "vcm", "hcm", "chcm", "pcr", "vsg", "alt", "ast", "ggt", "rm",
    "tac", "imc", "hba1c", "rdw", "mpv", "inr", "tp", "ttp", "bun", "adn", "vih", "cea", "fsh", "lh",
    "gh", "acth", "ft3", "ft4", "t3", "t4", "igg", "igm", "iga", "ige", "eps", "ips", "cc",
}
SMALL_WORDS = {"DE", "EN", "LA", "EL", "LOS", "LAS", "DEL", "Y", "O", "CON", "POR", "PARA", "UN", "UNA", "AL", "SU", "SUS"}
ACCENTS = {
    "globulos": "glóbulos", "hematies": "hematíes", "trigliceridos": "triglicéridos", "proteina": "proteína",
    "acido": "ácido", "urico": "úrico", "antigeno": "antígeno", "especifico": "específico",
    "prostatico": "prostático", "prostatica": "prostática", "neutrofilos": "neutrófilos",
    "eosinofilos": "eosinófilos", "basofilos": "basófilos", "indice": "índice", "magnetica": "magnética",
    "multiparametrica": "multiparamétrica", "ecografia": "ecografía", "tension": "tensión", "presion": "presión",
}
_CAPS_WORD = re.compile(r"[A-ZÁÉÍÓÚÑ0-9]{2,}(?:-[A-ZÁÉÍÓÚÑ0-9]+)*")


def tidy_question(text: str) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return ""

    def fix(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        bare = re.sub(r"[^a-záéíóúñ0-9]", "", lower)
        if bare == "hba1c":
            return "HbA1c"
        if bare in ACRONYMS:
            return word
        if len(word) == 2 and word not in SMALL_WORDS:
            return word
        if any(c.isdigit() for c in word) and any(c.isalpha() for c in word):
            return word
        if "-" in word:
            return word
        return lower.replace(bare, ACCENTS[bare]) if bare in ACCENTS else lower

    fixed = _CAPS_WORD.sub(fix, clean)
    # "BLANCOS Y PLAQUETAS": la Y u O suelta entre palabras ya en minúscula también se baja.
    fixed = re.sub(r"(?<=[a-záéíóúñ]) ([YO]) (?=[a-záéíóúñ])", lambda m: f" {m.group(1).lower()} ", fixed)
    return fixed[0].upper() + fixed[1:]
