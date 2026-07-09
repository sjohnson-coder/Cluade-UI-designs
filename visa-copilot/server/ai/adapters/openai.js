// OpenAI adapter — implements the common generateText interface used by the orchestrator.
export function createOpenAIAdapter({ apiKey, model = 'gpt-4o-mini' }) {
  return {
    name: 'openai',
    model,
    async generateText({ system, prompt, temperature = 0.4, maxTokens = 1200 }) {
      const res = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
        body: JSON.stringify({
          model,
          temperature,
          max_tokens: maxTokens,
          messages: [
            system ? { role: 'system', content: system } : null,
            { role: 'user', content: prompt },
          ].filter(Boolean),
        }),
      });
      if (!res.ok) throw new Error(`OpenAI error ${res.status}: ${await res.text()}`);
      const data = await res.json();
      return data.choices?.[0]?.message?.content?.trim() || '';
    },
  };
}
