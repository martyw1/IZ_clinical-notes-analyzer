import { ApiRequestError } from '../api/json'

class FileReadError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'FileReadError'
  }
}

export function messageForUploadError(error: unknown): string {
  if (error instanceof ApiRequestError || error instanceof FileReadError) return error.message
  if (error instanceof SyntaxError) return 'The selected file is not valid JSON.'
  return 'Unable to import the selected treatment-plan aggregate.'
}

export function readFileText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new FileReadError('Unable to read the selected file.'))
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result)
        return
      }
      reject(new FileReadError('The selected file did not contain readable text.'))
    }
    reader.readAsText(file)
  })
}
