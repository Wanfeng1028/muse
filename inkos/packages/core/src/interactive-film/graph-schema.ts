import { z } from "zod";

export const VarValueSchema = z.union([z.number(), z.string(), z.boolean()]);
export type VarValue = z.infer<typeof VarValueSchema>;

export const ConditionSchema = z.object({
  var: z.string().min(1),
  op: z.enum([">=", "<=", ">", "<", "==", "!="]),
  value: VarValueSchema,
}).strict();
export type Condition = z.infer<typeof ConditionSchema>;

export const EffectSchema = z.object({
  var: z.string().min(1),
  op: z.enum(["set", "add", "sub"]),
  value: VarValueSchema,
}).strict();
export type Effect = z.infer<typeof EffectSchema>;

export const ChoiceSchema = z.object({
  id: z.string().min(1),
  text: z.string(),
  targetNodeId: z.string().min(1),
  condition: ConditionSchema.optional(),
  effects: z.array(EffectSchema).default([]),
  weight: z.string().min(1).optional(),
}).strict();
export type Choice = z.infer<typeof ChoiceSchema>;

export const DialogueLineSchema = z.object({
  speaker: z.string(),
  text: z.string(),
  emotion: z.string().default(""),
  condition: ConditionSchema.optional(),
}).strict();
export type DialogueLine = z.infer<typeof DialogueLineSchema>;

export const ImageSlotSchema = z.object({
  prompt: z.string().default(""),
  assetRef: z.string().optional(),
}).strict();
export type ImageSlot = z.infer<typeof ImageSlotSchema>;

export const NodeTypeSchema = z.enum(["start", "normal", "branch", "merge", "ending", "explore"]);
export type NodeType = z.infer<typeof NodeTypeSchema>;

export const VoiceProfileSchema = z.object({
  speakingRhythm: z.string().default(""),
  vocabulary: z.string().default(""),
  sampleLines: z.array(z.string()).default([]),
}).strict();
export type VoiceProfile = z.infer<typeof VoiceProfileSchema>;

export const CharacterSchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  role: z.string().min(1).default("other"),
  motivation: z.string().default(""),
  voiceProfile: VoiceProfileSchema.optional(),
}).strict();
export type Character = z.infer<typeof CharacterSchema>;

export const WorldAnchorSchema = z.object({
  storyCore: z.string().default(""),
  theme: z.string().default(""),
  genre: z.string().default(""),
  worldRules: z.string().default(""),
  durationMinutes: z.number().default(0),
}).strict();
export type WorldAnchor = z.infer<typeof WorldAnchorSchema>;

export const StoryNodeSchema = z.object({
  id: z.string().min(1),
  title: z.string().default(""),
  type: NodeTypeSchema,
  sceneDesc: z.string().default(""),
  dialogue: z.array(DialogueLineSchema).default([]),
  choices: z.array(ChoiceSchema).default([]),
  imageSlot: ImageSlotSchema.optional(),
  act: z.string().default(""),
  position: z.object({ x: z.number(), y: z.number() }).strict().optional(),
}).strict();
export type StoryNode = z.infer<typeof StoryNodeSchema>;

export const VariableSchema = z.object({
  name: z.string().min(1),
  type: z.string().min(1),
  default: VarValueSchema,
  desc: z.string().default(""),
}).strict();
export type Variable = z.infer<typeof VariableSchema>;

export const EndingSchema = z.object({
  id: z.string().min(1),
  nodeId: z.string().min(1),
  title: z.string(),
  type: z.string().min(1),
  description: z.string().default(""),
}).strict();
export type Ending = z.infer<typeof EndingSchema>;

export const StoryGraphSchema = z.object({
  schemaVersion: z.literal(1),
  projectId: z.string().min(1),
  title: z.string(),
  worldAnchor: WorldAnchorSchema.optional(),
  characters: z.array(CharacterSchema).default([]),
  variables: z.array(VariableSchema).default([]),
  nodes: z.array(StoryNodeSchema).default([]),
  endings: z.array(EndingSchema).default([]),
}).strict();
export type StoryGraph = z.infer<typeof StoryGraphSchema>;
