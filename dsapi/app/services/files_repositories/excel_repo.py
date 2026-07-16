import pandas as pd
from .base import ITemplateRepository, QuestionTemplate
from typing import List


class ExcelTemplateRepository(ITemplateRepository):
    """Реализация загрузки шаблонов из Excel-файла"""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def get_all_templates(self) -> List[QuestionTemplate]:
        try:
            df = pd.read_excel(self.file_path)
            df = df.loc[df["id"] != 4]
            return [
                QuestionTemplate(
                    id=int(row['id']),
                    text=str(row['Шаблон'])
                )
                for _, row in df.iterrows()
            ]
        except Exception as e:
            print(f"Ошибка загрузки шаблонов из Excel: {e}")
            return []