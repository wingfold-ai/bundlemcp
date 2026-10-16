/** A management-API read that failed, with the status it failed with. */
export class QueryError extends Error {
  constructor(
    message: string,
    readonly status: number | undefined,
  ) {
    super(message);
  }
}

/** The data of an `openapi-fetch` result, or a thrown `QueryError` with the API's message. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    throw new QueryError(apiErrorMessage(result.error), result.response.status);
  }
  return result.data;
}
