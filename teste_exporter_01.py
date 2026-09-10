import pandas as pd


filepath = (
    "results/"
    "teste_exportador/"
    "transmission_loss.csv"
)


df = pd.read_csv(
    filepath
)


print()
print("====================================")
print("TESTE DO CSV DE TL")
print("====================================")

print()

print(
    df.head()
)

print()

print(
    f"Número de linhas: "
    f"{len(df)}"
)

print(
    f"Primeira frequência: "
    f"{df['frequency_Hz'].iloc[0]} Hz"
)

print(
    f"Última frequência: "
    f"{df['frequency_Hz'].iloc[-1]} Hz"
)

print()

print(
    "Colunas:"
)

for column in df.columns:

    print(
        f"  {column}"
    )