from source_code_analyzer.config import settings
from source_code_analyzer.data_types import CandidateFiles, RepositoryInfo


class LLMConfig:
    def __init__(self):
        config = settings
        self._base_config = {
            "model": config.TASK_MODEL_ID,
            "base_url": config.LLM_API_BASE,
            "api_type": "openai",
            "api_key": config.LLM_API_KEY,
        }

        self.openai_llm_config = self._create_llm_config(config, None)

        self.repo_id_llm_config = self._create_llm_config(config, response_format=RepositoryInfo)
        self.file_search_summarizer_llm_config = self._create_llm_config(
            config, response_format=CandidateFiles
        )

    def _create_llm_config(self, config, response_format):
        return {
            "config_list": [
                {
                    **self._base_config,
                    **({"response_format": response_format} if response_format else {}),
                    **({"default_headers": config.EXTRA_HEADERS} if config.EXTRA_HEADERS else {}),
                }
            ],
            "temperature": config.MODEL_TEMPERATURE,
        }
