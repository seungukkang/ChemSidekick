import { Action, ActionPanel, Detail, Icon, Keyboard, openExtensionPreferences } from "@raycast/api";
import { errorText } from "../lib/error-text";

// One screen for every failure: csk not reachable (TransportError) or csk
// reporting an error (ErrorInfo from an ErrorResponse).
export function ErrorView({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const text = errorText(error);
  return (
    <Detail
      navigationTitle={text.title}
      markdown={text.markdown}
      actions={
        <ActionPanel>
          {text.copyCommand && <Action.CopyToClipboard title="Copy Command" content={text.copyCommand} />}
          {text.showPreferences && (
            <Action title="Open Extension Preferences" icon={Icon.Gear} onAction={openExtensionPreferences} />
          )}
          {onRetry && <Action title="Try Again" icon={Icon.ArrowClockwise} onAction={onRetry} />}
          <Action.CopyToClipboard title="Copy Error" content={text.copyText} shortcut={Keyboard.Shortcut.Common.Copy} />
        </ActionPanel>
      }
    />
  );
}
