import { Type } from "@sinclair/typebox";

export const FoundationOutlineToolSchema = Type.Object({
  storyFrame: Type.String({ minLength: 1, description: "Concise readable foundation: premise, central conflict, motives, constraints and causal resolution. Keep detailed character cards and chapter prose for their own documents." }),
  volumeMap: Type.String({ minLength: 1, description: "Readable volume and chapter-direction Markdown covering the requested story, with brief causal beats for each chapter rather than drafted scenes." }),
});

export const BookRulesDataToolSchema = Type.Object({
  protagonist: Type.Optional(Type.Object({
    name: Type.String(),
    personalityLock: Type.Array(Type.String()),
    behavioralConstraints: Type.Array(Type.String()),
  })),
  genreLock: Type.Optional(Type.Object({
    primary: Type.String(),
    forbidden: Type.Array(Type.String()),
  })),
  narrativePerson: Type.Optional(Type.String({ description: "Narrative person in the user's own terms." })),
  prohibitions: Type.Array(Type.String()),
  enableFullCastTracking: Type.Boolean(),
  fanficMode: Type.Optional(Type.String()),
  allowedDeviations: Type.Array(Type.String()),
});

export const FoundationDetailsToolSchema = Type.Object({
  bookRules: Type.String({ minLength: 1, description: "Readable book-rules Markdown." }),
  bookRulesData: BookRulesDataToolSchema,
  pendingHooks: Type.Array(Type.Object({
    hookId: Type.String({ minLength: 1 }),
    type: Type.String({ minLength: 1 }),
    expectedPayoff: Type.String({ minLength: 1 }),
    notes: Type.String(),
  })),
});

export const FoundationCastIndexToolSchema = Type.Object({
  roles: Type.Array(Type.Object({
    tier: Type.Union([Type.Literal("major"), Type.Literal("minor")]),
    name: Type.String({ minLength: 1 }),
  }), { minItems: 1 }),
});

export function foundationCastDocumentsToolSchema(roles:readonly {name:string}[]) {
  return Type.Object(Object.fromEntries(roles.map((role,index)=>[
    `role_${index+1}_content`,
    Type.String({minLength:1,description:`Concise Markdown card for ${role.name}: present motive, knowledge, relationship pressure and limits relevant to the opening. Submit text directly.`}),
  ])),{additionalProperties:false});
}
