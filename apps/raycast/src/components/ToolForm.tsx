import { Action, ActionPanel, Alert, confirmAlert, Form, Icon, useNavigation } from "@raycast/api";
import { useState } from "react";
import type { ToolInfo } from "../lib/contract";
import { type FieldSpec, formDefaults, formSpec, type FormValues, toInput } from "../lib/form";
import { ResultView } from "./ResultView";

const TIMEOUT_FIELD = "__csk_timeout"; // heavy tools need a time limit (csk --timeout)

function Field({
  f,
  value,
  error,
  onChange,
}: {
  f: FieldSpec;
  value: string | boolean | undefined;
  error?: string;
  onChange: () => void;
}) {
  const common = { id: f.name, info: f.description || undefined, error, onChange };
  const text = typeof value === "string" ? value : String(f.default);
  switch (f.kind) {
    case "textarea":
      return <Form.TextArea {...common} title={f.label} defaultValue={text} enableMarkdown={false} />;
    case "checkbox":
      return <Form.Checkbox {...common} label={f.label} defaultValue={value === true} />;
    case "dropdown":
      return (
        <Form.Dropdown {...common} title={f.label} defaultValue={text || f.options[0]}>
          {f.options.map((o) => (
            <Form.Dropdown.Item key={o} value={o} title={o} />
          ))}
        </Form.Dropdown>
      );
    default: {
      const range = f.minimum !== undefined || f.maximum !== undefined ? `${f.minimum ?? ""}–${f.maximum ?? ""}` : "";
      return (
        <Form.TextField
          {...common}
          title={f.label}
          defaultValue={text}
          placeholder={f.required ? "Required" : range || (f.nullable ? "Optional" : undefined)}
        />
      );
    }
  }
}

// The input form of any tool, generated from its input JSON Schema. `input`
// fills it in (e.g. the previous run's input, or text from the clipboard).
export function ToolForm({
  tool,
  input,
  autoOpenViewer = false,
}: {
  tool: ToolInfo;
  input?: Record<string, unknown>;
  autoOpenViewer?: boolean;
}) {
  const { push } = useNavigation();
  const spec = formSpec(tool.input_schema);
  const initial = formDefaults(spec.fields, input);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const heavy = tool.resources === "heavy";

  async function submit(values: FormValues) {
    const { input, errors } = toInput(spec.fields, values);
    let timeoutS: number | undefined;
    if (heavy) {
      timeoutS = Number(values[TIMEOUT_FIELD]);
      if (!Number.isFinite(timeoutS) || timeoutS <= 0) errors[TIMEOUT_FIELD] = "Enter a time in seconds";
    }
    setErrors(errors);
    if (Object.keys(errors).length) return;
    if (heavy) {
      const ok = await confirmAlert({
        title: `${tool.title} is a heavy tool`,
        message: "It can use up to 4 CPU cores and 4 GB of memory. Run it?",
        primaryAction: { title: "Run", style: Alert.ActionStyle.Default },
      });
      if (!ok) return;
    }
    push(
      <ResultView tool={tool} input={input} options={{ confirmed: heavy, timeoutS }} autoOpenViewer={autoOpenViewer} />,
    );
  }

  const clear = (name: string) => () => {
    if (errors[name]) {
      setErrors((current) => {
        const next = { ...current };
        delete next[name];
        return next;
      });
    }
  };

  return (
    <Form
      navigationTitle={tool.title}
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Run" icon={Icon.Play} onSubmit={submit} />
        </ActionPanel>
      }
    >
      <Form.Description title={tool.id} text={tool.summary} />
      {spec.fields.map((f) => (
        <Field key={f.name} f={f} value={initial[f.name]} error={errors[f.name]} onChange={clear(f.name)} />
      ))}
      {heavy && (
        <Form.TextField
          id={TIMEOUT_FIELD}
          title="Time limit (s)"
          defaultValue="600"
          error={errors[TIMEOUT_FIELD]}
          onChange={clear(TIMEOUT_FIELD)}
        />
      )}
    </Form>
  );
}
