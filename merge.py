import boto3
import pandas as pd
import io

s3 = boto3.client("s3")
bucket = "anime-mal-scraper"
prefix = "output/"
merged_df = pd.DataFrame()

print("🔁 Iniciando merge de archivos .parquet...")

for i in range(1, 6):
    key = f"{prefix}output_users_{i}.parquet"
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        df = pd.read_parquet(io.BytesIO(obj["Body"].read()))

        if "user" not in df.columns or "anime_id" not in df.columns:
            print(f"⚠️ Archivo {key} no contiene las columnas requeridas.")
            continue

        df["anime_id"] = pd.to_numeric(df["anime_id"], errors="coerce").astype("Int64")
        df["score"] = pd.to_numeric(df["score"], errors="coerce")

        merged_df = pd.concat([merged_df, df])
        print(f"✔️ Agregado {key} con {df.shape[0]} filas")

    except Exception as e:
        print(f"❌ Error leyendo {key}: {e}")

# Limpiar duplicados
merged_df.drop_duplicates(subset=["user", "anime_id"], inplace=True)
print(f"📊 Total filas después del merge: {merged_df.shape[0]}")

# Guardar y subir
merged_output_path = "merged_output.parquet"
merged_df.to_parquet(merged_output_path, index=False)

s3.upload_file(merged_output_path, bucket, f"{prefix}merged_output.parquet")
print("🎉 Merge final subido a S3 como 'merged_output.parquet'")