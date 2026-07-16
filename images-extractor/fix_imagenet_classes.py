input_file = "imagenet_classes.txt"
output_file = "imagenet_classes_fixed.txt"

with open(input_file, "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f.readlines() if line.strip()]

with open(output_file, "w", encoding="utf-8") as f:
    for idx, line in enumerate(lines):
        f.write(f"{idx} {line}\n")

print(f"Готово: {output_file}")