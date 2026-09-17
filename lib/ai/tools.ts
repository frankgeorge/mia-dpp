import OpenAI from "openai";

export const PROPOSE_MAPPINGS_TOOL: OpenAI.ChatCompletionTool = {
  type: "function",
  function: {
    name: "propose_mappings",
    description:
      "Propose field mappings from the user's product data onto the IDTA Digital Nameplate submodel. Call this once per product description.",
    parameters: {
      type: "object",
      properties: {
        productName: {
          type: "string",
          description: "Short human-readable product name for this passport.",
        },
        mappings: {
          type: "array",
          items: {
            type: "object",
            properties: {
              sourceField: {
                type: "string",
                description:
                  "Field name as it would appear in the manufacturer's own system.",
              },
              sourceValue: { type: "string", description: "The value provided by the user." },
              targetElement: {
                type: "string",
                description: "Exact name of the target Digital Nameplate element.",
              },
              confidence: {
                type: "number",
                description: "Honest confidence from 0 to 1.",
              },
              reasoning: {
                type: "string",
                description: "One sentence on why this mapping was chosen.",
              },
            },
            required: [
              "sourceField",
              "sourceValue",
              "targetElement",
              "confidence",
              "reasoning",
            ],
          },
        },
      },
      required: ["productName", "mappings"],
    },
  },
};

export const GENERATE_DPP_TOOL: OpenAI.ChatCompletionTool = {
  type: "function",
  function: {
    name: "generate_dpp",
    description:
      "Assemble the Digital Product Passport from the mappings the user has approved. Only call when the user asks to generate or export.",
    parameters: {
      type: "object",
      properties: {
        confirm: { type: "boolean", description: "Always true." },
      },
      required: ["confirm"],
    },
  },
};

/** Tools for routes that only propose mappings (no generate_dpp) */
export const PROPOSE_ONLY_TOOLS: OpenAI.ChatCompletionTool[] = [
  PROPOSE_MAPPINGS_TOOL,
];

/** Full tool set for the chat route (propose + generate) */
export const CHAT_TOOLS: OpenAI.ChatCompletionTool[] = [
  PROPOSE_MAPPINGS_TOOL,
  GENERATE_DPP_TOOL,
];
