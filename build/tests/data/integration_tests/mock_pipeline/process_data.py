import pandas as pd
from pathlib import Path


def process_csv(input_path: str):
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    df = pd.read_csv(input_path)

    # Basic cleaning
    df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]
    df = df.drop_duplicates()

    # Fill missing values
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].fillna(df[col].mean())
        else:
            df[col] = df[col].fillna("unknown")

    # Target variable
    y = df["age"]

    # Features
    X = df.drop(columns=["age"])

    return X, y


if __name__ == "__main__":
    X, y = process_csv("mock_data.csv")

    print("Features:")
    print(X.head())

    print("\nTarget:")
    print(y.head())