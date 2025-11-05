from k8s_debug_agent.config import settings
from k8s_debug_agent.data_types import CriticDecision, Plan, Step


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

        self.planner_llm_config = self._create_llm_config(config, response_format=Plan)
        self.critic_llm_config = self._create_llm_config(
            config, response_format=CriticDecision
        )
        self.reflection_llm_config = self._create_llm_config(
            config, response_format=Step
        )

    def _create_llm_config(self, config, response_format):
        return {
            "config_list": [
                {
                    **self._base_config,
                    **({"response_format": response_format} if response_format else {}),
                    **(
                        {"default_headers": config.EXTRA_HEADERS}
                        if config.EXTRA_HEADERS
                        else {}
                    ),
                }
            ],
            "temperature": config.MODEL_TEMPERATURE,
        }
