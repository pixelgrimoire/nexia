import math
import os
import re
from functools import lru_cache
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import make_pipeline

MODEL_VERSION = "0.1.0"
_MIN_SCORE = float(os.getenv("NLP_MIN_SCORE", "0.32"))
_DEFAULT_LABEL = os.getenv("NLP_DEFAULT_LABEL", "default")

_INTENT_SAMPLES = [
    ("hola", "greeting"),
    ("hola, buen día", "greeting"),
    ("buenas tardes", "greeting"),
    ("buenas noches", "greeting"),
    ("qué tal", "greeting"),
    ("hey, cómo están", "greeting"),
    ("cuál es el precio?", "pricing"),
    ("cuánto cuesta", "pricing"),
    ("me pasas la lista de precios", "pricing"),
    ("planes y tarifas", "pricing"),
    ("costo mensual", "pricing"),
    ("necesito soporte", "support"),
    ("no funciona", "support"),
    ("tengo un problema", "support"),
    ("ayuda por favor", "support"),
    ("la app marca error", "support"),
    ("quiero hablar con un humano", "handoff"),
    ("pásame con un asesor", "handoff"),
    ("puedo hablar con un agente", "handoff"),
    ("necesito atención humana", "handoff"),
    ("derivar a humano", "handoff"),
    ("quiero comprar", "sales"),
    ("me interesa contratar", "sales"),
    ("puedo agendar una demo", "sales"),
    ("quiero una cotización", "sales"),
    ("cómo me registro", "sales"),
    ("gracias", "gratitude"),
    ("muchas gracias", "gratitude"),
    ("mil gracias", "gratitude"),
    ("se agradece", "gratitude"),
    ("excelente, gracias", "gratitude"),
    ("adiós", "goodbye"),
    ("hasta luego", "goodbye"),
    ("nos vemos", "goodbye"),
    ("chau", "goodbye"),
    ("bye", "goodbye"),
    ("qué es esto?", "default"),
    ("no entiendo", "default"),
    ("podrías repetir", "default"),
    ("información", "default"),
    ("ok", "default"),
]


def _augment_samples() -> List[tuple[str, str]]:
    expanded: List[tuple[str, str]] = []
    for text, label in _INTENT_SAMPLES:
        expanded.append((text.lower(), label))
        expanded.append((text.lower().strip("?!¡¿"), label))
    # Lightweight synthetic variants for pricing/support intents
    templates = {
        "pricing": [
            "precio de {product}",
            "tarifa {product}",
            "plan {product}",
            "cuánto vale {product}",
        ],
        "support": [
            "no puedo acceder", "falló el sistema", "problema con {product}", "error al enviar mensaje",
        ],
        "sales": [
            "quiero activar {product}", "cómo compro {product}",
        ],
    }
    products = ["nexia", "la cuenta", "el servicio", "la plataforma"]
    for label, phrases in templates.items():
        for base in phrases:
            for product in products:
                expanded.append((base.format(product=product), label))
    return expanded


@lru_cache(maxsize=1)
def _load_pipeline():
    samples = _augment_samples()
    texts = [t for t, _ in samples]
    labels = [l for _, l in samples]
    pipeline = make_pipeline(
        TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1),
        ComplementNB(alpha=0.3),
    )
    pipeline.fit(texts, labels)
    return pipeline


class IntentScore(BaseModel):
    label: str
    score: float


class IntentRequest(BaseModel):
    text: str = Field(..., description="Mensaje a clasificar")
    candidates: Optional[List[str]] = Field(
        default=None, description="Opcional: restringir a intentos permitidos"
    )
    top_k: int = Field(3, ge=1, le=10)
    org_id: Optional[str] = Field(
        default=None, description="Reservado: permite modelos por organización"
    )


class IntentResponse(BaseModel):
    top_intents: List[IntentScore]
    primary_intent: str
    model_version: str = MODEL_VERSION


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\d{2,4}[\s-]?){2,4}\d{2,4}")
NAME_PATTERNS = [
    re.compile(r"me llamo ([\wÁÉÍÓÚÑáéíóúñ ]{2,40})", re.IGNORECASE),
    re.compile(r"mi nombre es ([\wÁÉÍÓÚÑáéíóúñ ]{2,40})", re.IGNORECASE),
    re.compile(r"soy ([\wÁÉÍÓÚÑáéíóúñ ]{2,40})", re.IGNORECASE),
]


class ExtractRequest(BaseModel):
    text: str


class ExtractResponse(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    raw_matches: dict[str, Optional[str]]


app = FastAPI(title="NexIA NLP Service", version=MODEL_VERSION)


def _normalize_label(label: str) -> str:
    return (label or "").strip().lower().replace(" ", "_")


def _choose_default(label: Optional[str], score: float) -> str:
    if not label or math.isnan(score) or score < _MIN_SCORE:
        return _DEFAULT_LABEL
    return label


@app.post("/api/nlp/intents", response_model=IntentResponse)
def classify_intent(payload: IntentRequest):
    text = (payload.text or "").strip()
    if not text:
        return IntentResponse(
            top_intents=[IntentScore(label=_DEFAULT_LABEL, score=1.0)],
            primary_intent=_DEFAULT_LABEL,
        )

    pipeline = _load_pipeline()
    raw_scores = pipeline.predict_proba([text.lower()])[0]
    classes = list(pipeline.classes_)
    scored = list(zip(classes, raw_scores))

    if payload.candidates:
        allowed = {_normalize_label(c) for c in payload.candidates}
        scored = [item for item in scored if _normalize_label(item[0]) in allowed]

    scored.sort(key=lambda item: item[1], reverse=True)
    top_items = scored[: payload.top_k] if scored else [( _DEFAULT_LABEL, 1.0 )]

    top_intents = [
        IntentScore(label=_normalize_label(label), score=float(score))
        for label, score in top_items
    ]
    primary_label = top_intents[0].label if top_intents else _DEFAULT_LABEL
    primary_score = top_intents[0].score if top_intents else 1.0
    primary = _choose_default(primary_label, primary_score)

    if primary == _DEFAULT_LABEL and primary_label != _DEFAULT_LABEL:
        top_intents.insert(0, IntentScore(label=_DEFAULT_LABEL, score=1.0 - primary_score))

    return IntentResponse(
        top_intents=top_intents,
        primary_intent=primary,
    )


@app.post("/api/nlp/extract", response_model=ExtractResponse)
def extract_entities(payload: ExtractRequest):
    text = payload.text or ""
    email = None
    phone = None
    name = None

    email_match = EMAIL_RE.search(text)
    if email_match:
        email = email_match.group(0)

    phone_match = PHONE_RE.search(text)
    if phone_match:
        raw_phone = re.sub(r"[^\d+]", "", phone_match.group(0))
        if 7 <= len(raw_phone) <= 15:
            phone = raw_phone

    lowered = text.lower()
    for pattern in NAME_PATTERNS:
        match = pattern.search(lowered)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(r"[^\wÁÉÍÓÚÑáéíóúñ\s]", "", candidate)
            if 1 <= len(candidate.split()) <= 4:
                name = candidate.title()
                break

    return ExtractResponse(
        email=email,
        phone=phone,
        name=name,
        raw_matches={"email": email, "phone": phone, "name": name},
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "model_version": MODEL_VERSION}
