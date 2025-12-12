import pandas as pd
df = pd.DataFrame({'Price': [1.5, 2.0, 1.456]})
csv_decimal = ','
print("--- With float_format='%.2f' ---")
print(df.to_csv(sep=';', decimal=csv_decimal, float_format='%.2f', index=False))
print("\n--- Without float_format ---")
print(df.to_csv(sep=';', decimal=csv_decimal, index=False))
