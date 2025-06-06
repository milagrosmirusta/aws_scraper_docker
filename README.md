
# 🕵️ Anime Completed List Scraper (MyAnimeList) [Docker + AWS Ready]

Este proyecto permite scrapear en paralelo las listas de animes completados de usuarios de [MyAnimeList](https://myanimelist.net), y guardar los datos estructurados como `.parquet` para análisis o sistemas de recomendación.

---

## 📦 Estructura del Proyecto

```
aws_scraper_docker/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── scraping_anime.py        # Script principal de scraping
├── merge.py                 # Script para unir todos los .parquet
├── users/                   # Contiene los archivos users_X.txt
│   ├── users_1.txt
│   ├── ...
└── output/                  # Resultados y errores (montado por volumen)
```

---

## 🚀 Cómo correrlo en AWS EC2

1. Cloná el repo:
```bash
git clone https://github.com/tuusuario/aws_scraper_docker.git
cd aws_scraper_docker
```

2. Ejecutá todos los scrapers y el merge:
```bash
docker-compose up --build -d
```

---

## 🛠 Requisitos

- Docker instalado
- AWS credentials disponibles (por IAM o `~/.aws/credentials`)
- Bucket S3 llamado `anime-mal-scraper`

---

## 📤 Qué hace cada contenedor

- `scraper1` a `scraper5`: leen batches de usuarios desde `/users/users_X.txt`
- Guardan resultados parciales en `output/output_users_X.parquet`
- Suben a S3 (resultados, errores y progreso)
- `merger`: une todos los `.parquet` en `merged_output.parquet` y lo sube a S3

---

## 📚 Campos en el dataset

- `user`: nombre de usuario de MAL
- `anime_id`: ID numérico del anime en MAL
- `title`: título del anime
- `score`: puntaje que dio el usuario

---

## 🧠 Ideal para...

- Sistemas de recomendación
- Análisis de gustos por usuario
- Enriquecimiento con Jikan API por `anime_id`

---

## ✨ Autor

Proyecto de especialización - Milagros Irusta

---

⚠️ Este proyecto es educativo. No contiene credenciales ni datos privados.
Los usuarios utilizados fueron generados con fines de prueba.
