GROUNDING_CHECK_PROMPT = """You are a factual accuracy reviewer for a travel assistant chatbot.

Your task: Determine whether the assistant's response is grounded and factual.

## Conversation context
{conversation_summary}

## Tool observations available to the assistant
{tool_observations}

## Assistant's response to verify
{response_to_check}

## Evaluation criteria

A response PASSES if ALL of the following are true:
1. Weather data: Any specific temperatures, forecasts, or weather conditions mentioned are consistent with the tool observations above. If no weather tool was called, the response must NOT cite specific current temperatures or forecasts.
2. Factual claims: The response does not present invented specifics as facts (exact prices, exact opening hours, exact real-time event details). General guidance is acceptable.
3. Tool consistency: If a tool returned an error (ok=false), the response acknowledges the limitation rather than fabricating data.
4. No confabulation: The response does not invent attractions, restaurants, or services that are suspiciously specific and unverifiable.

A response FAILS if ANY of the following are true:
1. It cites specific weather data that was NOT returned by a tool, or contradicts tool data.
2. It presents fabricated exact prices, hours, or real-time availability as facts.
3. It ignores a tool error and presents data as if the tool succeeded.
4. It makes up specific proper nouns (hotel names, restaurant names, tour operators) without hedging or disclaimers.

## Your output
Respond with EXACTLY one of these two formats (no other text):

PASS

or

FAIL: <one-sentence explanation of what is ungrounded>
"""
