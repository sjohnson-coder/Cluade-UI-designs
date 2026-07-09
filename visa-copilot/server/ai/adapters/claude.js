// Claude (Anthropic) adapter — implements the common generateText interface.
export function createClaudeAdapter({ apiKey, model = 'claude-sonnet-5' }) {
  return {
    name: 'claude',
    model,
    async generateText({ system, prompt, temperature = 0.4, maxTokens = 1200 }) {
      const res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
        },
        body: JSON.stringify({
          model,
          max_tokens: maxTokens,
          temperature,
          system: system || undefined,
          messages: [{ role: 'user', content: prompt }],
        }),
      });
      if (!res.ok) throw new Error(`Anthropic error ${res.status}: ${await res.text()}`);
      const data = await res.json();
      return (data.content || []).map((b) => b.text || '').join('').trim();
    },
  };
}
