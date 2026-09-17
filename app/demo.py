"""Datos de demostración para probar el flujo completo sin llaves. Todo queda marcado is_demo."""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import delete

from app.db import Ad, Product, session_scope, utcnow
from app.mapping import slugify
from app.services.scorer import apply

DEMO = [
    # nombre, categoría, días, anunciantes, anuncios, viabilidad, problema, ángulo, hooks, países
    ("corrector de postura", "salud y bienestar", 46, 6, 14, 8.0, "Dolor de espalda por trabajar sentado",
     "Alivio de espalda en 7 días sin ir al fisioterapeuta",
     ["Tu espalda te lo va a agradecer", "Deja de encorvarte sin darte cuenta", "10 minutos al día y listo"],
     ["DO", "CO", "MX"]),
    ("selladora de bolsas portátil", "cocina", 38, 5, 11, 8.5, "Comida y snacks que se ponen blandos",
     "Tu comida fresca por semanas con un clic",
     ["Nunca más snacks blandos", "Cierra cualquier bolsa en segundos", "El truco de cocina más barato"],
     ["DO", "MX"]),
    ("limpiador de oídos con cámara", "salud y bienestar", 33, 4, 9, 7.5, "Limpiar oídos sin ver lo que haces",
     "Mira dentro de tu oído desde el celular",
     ["No vas a creer lo que tenía", "Adiós a los hisopos", "Limpieza segura viendo en vivo"],
     ["CO", "MX"]),
    ("organizador de cables magnético", "hogar", 21, 3, 6, 7.0, "Cables enredados en el escritorio",
     "Escritorio ordenado en 30 segundos",
     ["Tus cables nunca más al piso", "El orden que tu escritorio pedía", "Pégalo y olvídate"],
     ["DO", "CO"]),
    ("cepillo quita pelo de mascotas", "mascotas", 52, 7, 18, 8.0, "Pelo de mascota en muebles y ropa",
     "Sofá sin pelos de perro en una pasada",
     ["Mira cuánto pelo salió", "Sin rodillos que se acaban", "Tu sofá como nuevo"],
     ["DO", "CO", "MX"]),
    ("faja reductora con tallas", "belleza", 60, 8, 20, 3.5, "Moldear la figura",
     "Cintura marcada al instante", ["Resultados desde el primer día", "Se ajusta a tu cuerpo", "Úsala debajo de la ropa"],
     ["DO", "CO"]),
    ("lámpara de proyección galaxia", "hogar", 12, 2, 4, 6.5, "Habitación aburrida para niños",
     "Convierte el cuarto de tus hijos en el espacio",
     ["Tus hijos se van a dormir solos", "El cuarto más bonito del barrio", "Luces que calman"],
     ["MX"]),
    ("aspiradora portátil para carro", "autos", 27, 4, 8, 7.0, "Carro sucio sin tiempo para lavarlo",
     "Carro limpio sin ir al car wash",
     ["Tu carro limpio en 5 minutos", "Potencia de verdad sin cables", "Arena y migas fuera"],
     ["DO", "CO"]),
    ("rodillo facial de hielo", "belleza", 9, 1, 2, 6.0, "Cara hinchada en la mañana",
     "Despierta con la cara desinflamada", ["El secreto de las coreanas", "Adiós ojeras hinchadas", "Frío que despierta"],
     ["CO"]),
    ("dispensador de pasta dental automático", "hogar", 18, 3, 5, 6.5, "Tubo de pasta desperdiciado y baño sucio",
     "Baño ordenado y cero desperdicio",
     ["El baño de tus sueños", "Una mano y listo", "Tus hijos van a querer cepillarse"],
     ["DO", "MX"]),
]

ADVERTISERS = ["Tienda Express RD", "Compra Fácil", "Oferta Top", "Casa Práctica", "Mundo Útil", "Todo en Casa",
               "Envío Gratis Ya", "Descuentos 24h", "Hogar Smart", "La Novedad"]


def seed() -> int:
    rng = random.Random(7)
    now = utcnow()
    with session_scope() as session:
        session.execute(delete(Ad).where(Ad.source == "demo"))
        session.execute(delete(Product).where(Product.is_demo.is_(True)))
        session.flush()

        for name, cat, days, n_adv, n_ads, via, problem, angle, hooks, countries in DEMO:
            product = Product(
                slug=slugify(name), name=name, category=cat, problem=problem, angle=angle, hooks=hooks,
                viability_ai=via, wow=int(via), has_sizes="tallas" in name, fragile=False, weight="ligero",
                is_demo=True,
            )
            session.add(product)
            advertisers = rng.sample(ADVERTISERS, n_adv)
            for i in range(n_ads):
                start = now - timedelta(days=rng.randint(max(1, days // 3), days))
                session.add(Ad(
                    source="demo", external_id=f"demo-{slugify(name)}-{i}",
                    country=countries[i % len(countries)], advertiser=advertisers[i % n_adv],
                    text=f"{angle}. Pago contra entrega y envío gratis.", started_at=start,
                    first_seen=now - timedelta(days=2), last_seen=now, is_active=True,
                    is_product=True, normalized_at=now, product=product,
                ))
            session.flush()
            apply(product)
        return len(DEMO)
