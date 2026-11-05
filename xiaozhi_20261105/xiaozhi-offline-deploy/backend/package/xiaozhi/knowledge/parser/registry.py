"""文档处理器注册表。"""

PROCESSOR_TYPES = {
    "rapid_ocr": ("xiaozhi.knowledge.parser.rapid_ocr", "RapidOCRParser"),
    "mineru_ocr": ("xiaozhi.knowledge.parser.mineru", "MinerUParser"),
    "mineru_official": ("xiaozhi.knowledge.parser.mineru_official", "MinerUOfficialParser"),
    "pp_structure_v3_ocr": ("xiaozhi.knowledge.parser.pp_structure_v3", "PPStructureV3Parser"),
    "deepseek_ocr": ("xiaozhi.knowledge.parser.deepseek_ocr", "DeepSeekOCRParser"),
    "paddleocr_vl_1_6": ("xiaozhi.knowledge.parser.paddleocr_api", "PaddleOCRVLParser"),
    "paddleocr_pp_ocrv6": ("xiaozhi.knowledge.parser.paddleocr_api", "PaddleOCRPPOCRv6Parser"),
}
