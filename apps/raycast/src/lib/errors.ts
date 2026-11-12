// Problems reaching csk at all (as opposed to csk reporting an error in JSON,
// which is an ErrorResponse). Each kind gets its own screen and hint.

export type TransportErrorKind =
  | "not_found" // no executable csk at any known path
  | "timeout" // csk ran longer than the safety limit
  | "usage" // exit code 2: csk did not understand the command (extension and csk disagree)
  | "reinstall" // csk could not start (missing Python module), usually after a dependency change
  | "not_json" // csk printed something that is not a contract response
  | "contract_mismatch"; // csk speaks a different contract version

export class TransportError extends Error {
  constructor(
    readonly kind: TransportErrorKind,
    message: string,
    readonly detail = "",
  ) {
    super(message);
    this.name = "TransportError";
  }
}

export function isTransportError(e: unknown): e is TransportError {
  return e instanceof TransportError;
}
