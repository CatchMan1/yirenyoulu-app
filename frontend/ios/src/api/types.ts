import type { components } from './generated';
export type Models = components['schemas'];
export type Model<K extends keyof Models> = Models[K];
export type Kind = 'attraction' | 'hotel' | 'restaurant';
export type Query = Record<
  string,
  string | number | boolean | readonly string[] | null | undefined
>;
