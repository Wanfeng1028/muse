import type {TSchema} from '@sinclair/typebox';
import {Value} from '@sinclair/typebox/value';

/** Decode only valid JSON explicitly supplied in object/array tool fields. Never repair prose. */
export function decodeStructuredFields(schema:TSchema,value:unknown,paths:string[]=[],path=''):unknown {
  if(typeof value==='string'&&(schema.type==='object'||schema.type==='array')){
    try{
      const decoded=JSON.parse(value);
      if(Value.Check(schema,decoded)){paths.push(path||'/');return decoded;}
    }catch{/* Keep the original value so normal validation reports the error. */}
    return value;
  }
  if(schema.type==='array'&&Array.isArray(value)&&schema.items)return value.map((v,i)=>decodeStructuredFields(schema.items,v,paths,`${path}/${i}`));
  if(schema.type==='object'&&value&&typeof value==='object'&&!Array.isArray(value))return Object.fromEntries(Object.entries(value).map(([key,v])=>[key,schema.properties?.[key]?decodeStructuredFields(schema.properties[key],v,paths,`${path}/${key}`):v]));
  return value;
}
