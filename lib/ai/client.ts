import OpenAI from "openai";

export function createAIClient(): OpenAI {
  return new OpenAI({
    apiKey: process.env.OPENROUTER_API_KEY!,
    baseURL: "https://openrouter.ai/api/v1",
    defaultHeaders: {
      "HTTP-Referer": "https://mia-dpp.vercel.app",
      "X-Title": "MIA Digital Product Passport",
    },
  });
}

export const MODEL = "deepseek/deepseek-chat-v3-0324";
