import './util';
import { externalThing } from 'some-lib';

export interface Sample {
  id: string;
}

export type SampleId = string;

export const sampleName = 'sample';

export function sampleFunction(value: string) {
  return value;
}

export class SampleClass {
  run() {
    return true;
  }
}
