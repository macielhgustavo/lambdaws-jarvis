# FreeLLMAPI provider onboarding for Jarvis

Jarvis talks to one local FreeLLMAPI endpoint. FreeLLMAPI then routes across every provider key registered in its dashboard. Secrets stay outside Git.

Run the importer after adding keys:

```bash
cd /home/gustavomaciel/.local/share/lambdaws-jarvis
node scripts/import-freellmapi-keys.mjs
```

By default it reads:

- `/home/gustavomaciel/.config/freellmapi/provider-keys.env`
- `/home/gustavomaciel/.config/lambdaws-jarvis/provider-keys.env`
- `/home/gustavomaciel/.config/lambdaws-jarvis/secrets.env`

It never prints API keys. It enables keyless providers automatically and imports any provider variables it finds.

## Already enabled without accounts

- `kilo` — anonymous free routes, low rate limits
- `ovh` — anonymous free routes, very low rate limits
- `aihorde` — anonymous volunteer queue, slower but useful as fallback

## First providers worth creating

These usually give the best free-token return for the least account friction:

| Provider | Env var | Notes |
| --- | --- | --- |
| Groq | `GROQ_API_KEY` | Fast free inference; good first key. |
| Google Gemini | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | High free-tier value; model catalog is strong. |
| Cerebras | `CEREBRAS_API_KEY` | Very fast inference on supported models. |
| NVIDIA NIM | `NVIDIA_API_KEY` | Strong models, may require NVIDIA account. |
| Hugging Face Router | `HF_TOKEN` or `HUGGINGFACE_API_KEY` | Small recurring free router credit. |
| Mistral | `MISTRAL_API_KEY` | Useful general fallback. |
| OpenRouter | `OPENROUTER_API_KEY` | Free model aliases; watch provider-side limits. |
| Cohere | `COHERE_API_KEY` | Useful for command/chat and rerank-style models. |
| Cloudflare Workers AI | `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` | Importer stores as `account_id:token`. |
| GitHub Models | `GITHUB_MODELS_API_KEY`, `GITHUB_TOKEN`, or `GH_TOKEN` | Good if the account has Models access. |

## Extra no-card/free gateways to add after the main set

Use the env var listed here and rerun the importer.

| Provider | Env var examples |
| --- | --- |
| AnyAPI | `ANYAPI_API_KEY` |
| AINative Studio | `AINATIVE_API_KEY` |
| Aion Labs | `AION_API_KEY` |
| Agnes AI | `AGNES_API_KEY` |
| BazaarLink | `BAZAARLINK_API_KEY` |
| ElectronHub | `ELECTRONHUB_API_KEY` |
| Experiential Labs | `EXPERIENTIAL_API_KEY` |
| LLM7 | `LLM7_API_KEY` |
| LongCat | `LONGCAT_API_KEY` |
| NavyAI | `NAVY_API_KEY` |
| NaraRouter | `NARA_API_KEY` |
| OrcaRouter | `ORCAROUTER_API_KEY` |
| Pollinations | `POLLINATIONS_API_KEY` |
| Requesty | `REQUESTY_API_KEY` |
| Routeway | `ROUTEWAY_API_KEY` |
| SEA-LION | `SEALION_API_KEY` |
| SiliconFlow | `SILICONFLOW_API_KEY` |
| UnoRouter | `UNOROUTER_API_KEY` |
| xKiro | `XKIRO_API_KEY` |
| Zhipu/Z.ai | `ZHIPU_API_KEY` |

Some providers require Discord, Telegram, Google sign-in, phone, payment method, or real-name verification. The importer can register keys once they exist, but it cannot bypass those interactive checks.
