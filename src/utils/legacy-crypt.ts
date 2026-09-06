// Dead code utility - orphan file with no inward edges
export function legacyEncrypt(text: string): string {
  let res = '';
  for (let i = 0; i < text.length; i++) {
    res += String.fromCharCode(text.charCodeAt(i) ^ 0x5a);
  }
  return res;
}

export function legacyDecrypt(cipher: string): string {
  return legacyEncrypt(cipher);
}
