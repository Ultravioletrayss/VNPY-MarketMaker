import pandas as pd

file_path = r"C:\Users\ultra\Desktop\CSV_DATA\FU2505.03.csv"

df = pd.read_csv(file_path, nrows=5)
print(df.columns.tolist())
print(df.head())