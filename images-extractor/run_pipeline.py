import os
from init_pipeline import Pipeline

FEATURE_JSON = os.getenv("FEATURE_JSON", "objects/feature.json")
OFF_EXCEL = os.getenv("OFF_EXCEL", "objects/OFF_actual.xlsx")
YOLO_CLASSES_JSON = os.getenv("YOLO_CLASSES_JSON", "objects/flora_fauna_classes.json")
ALL_OBJECTS_EXCEL = os.getenv("ALL_OBJECTS_EXCEL", "objects/All_Objects.xlsx")
PROMPT_PATH = os.getenv("PROMPT_PATH", "objects/Промт2.txt")

if __name__ == "__main__":
    pipeline = Pipeline(
        file_path=FEATURE_JSON,
        file_yolo_path=YOLO_CLASSES_JSON,
        file_promt_path=PROMPT_PATH
    )

    pipeline.run(
        excel_path=ALL_OBJECTS_EXCEL,
        off=OFF_EXCEL
    )
