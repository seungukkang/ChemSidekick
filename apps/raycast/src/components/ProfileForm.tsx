// Energy Profile (ENE-01): fill in the paths (A → TS → product) and pick the
// options from dropdowns; ⌘↵ draws the profile with its results. "Change Input"
// on the result comes back here with every value kept. The last input is
// remembered for the next time.
import { Action, ActionPanel, Detail, Form, Icon, Keyboard, useNavigation } from "@raycast/api";
import { useCachedState } from "@raycast/utils";
import type { ToolInfo } from "../lib/contract";
import {
  EXAMPLE_STATE,
  MAX_PATHS,
  type PathRow,
  productFieldTitle,
  profileInput,
  type ProfileState,
  solventChoices,
  TEMPERATURE_PRESETS,
  tsFieldTitle,
} from "../lib/profile";
import { ErrorView } from "./ErrorView";
import { ResultView } from "./ResultView";
import { useToolInfo } from "./use-tool";

const PROFILE_WIDTH = 640; // px: the drawing across the Detail view

export function ProfileCommand() {
  const { tool, error, revalidate } = useToolInfo("profile");
  if (error) return <ErrorView error={error} onRetry={revalidate} />;
  if (!tool) return <Detail isLoading markdown="Starting…" />;
  return <ProfileForm tool={tool} />;
}

export function ProfileForm({ tool }: { tool: ToolInfo }) {
  const { push, pop } = useNavigation();
  const [s, setS] = useCachedState<ProfileState>("profile-form", EXAMPLE_STATE);
  const set = (patch: Partial<ProfileState>) => setS({ ...s, ...patch });
  const setPath = (i: number, patch: Partial<PathRow>) =>
    set({ paths: s.paths.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const reaction = s.mode === "reaction";
  const bimolecular = s.molecularity === "bimolecular";

  const draw = () => push(<ResultView tool={tool} input={profileInput(s)} drawingWidth={PROFILE_WIDTH} onEdit={pop} />);

  return (
    <Form
      navigationTitle="Energy Profile"
      actions={
        <ActionPanel>
          <Action title="Draw Profile" icon={Icon.LineChart} onAction={draw} />
          {reaction && (
            <ActionPanel.Section>
              <Action
                title="Add Path"
                icon={Icon.Plus}
                shortcut={Keyboard.Shortcut.Common.New}
                onAction={() =>
                  s.paths.length < MAX_PATHS && set({ paths: [...s.paths, { name: "", ts: "", product: "" }] })
                }
              />
              {s.paths.length > 1 && (
                <Action
                  title="Remove Last Path"
                  icon={Icon.Minus}
                  shortcut={Keyboard.Shortcut.Common.Remove}
                  onAction={() => set({ paths: s.paths.slice(0, -1) })}
                />
              )}
            </ActionPanel.Section>
          )}
          <Action
            title="Reset to Example"
            icon={Icon.ArrowCounterClockwise}
            shortcut={{ modifiers: ["cmd", "shift"], key: "r" }}
            onAction={() => setS(EXAMPLE_STATE)}
          />
        </ActionPanel>
      }
    >
      <Form.Dropdown
        id="mode"
        title="Mode"
        value={s.mode}
        onChange={(v) =>
          set({ mode: v as ProfileState["mode"], unit: v === "reaction" && s.unit === "Eh" ? "kcal/mol" : s.unit })
        }
      >
        <Form.Dropdown.Item value="reaction" title="Reaction: A → TS → products" />
        <Form.Dropdown.Item value="populations" title="Populations: states (conformers)" />
      </Form.Dropdown>

      {reaction && (
        <>
          <Form.Description text="Energies relative to the reactant A (0). Leave a value empty if it is unknown. ⌘N adds a path." />
          {s.paths.map((p, i) => (
            <PathFields key={i} index={i} row={p} state={s} onChange={(patch) => setPath(i, patch)} />
          ))}
          <Form.Separator />
          <Form.Dropdown id="tsValues" title="TS values are" value={s.tsValues} onChange={(v) => set({ tsValues: v })}>
            <Form.Dropdown.Item value="barrier" title="Barriers ΔG‡" />
            <Form.Dropdown.Item value="rate constant" title="Rate constants k" />
            <Form.Dropdown.Item value="half-life" title="Half-lives t½" />
          </Form.Dropdown>
          <Form.Dropdown
            id="productValues"
            title="Product values are"
            value={s.productValues}
            onChange={(v) => set({ productValues: v })}
          >
            <Form.Dropdown.Item value="free energy" title="Free energies ΔG" />
            <Form.Dropdown.Item value="equilibrium constant" title="Equilibrium constants K" />
          </Form.Dropdown>
        </>
      )}

      {!reaction && (
        <Form.TextArea
          id="states"
          title="States"
          value={s.states}
          onChange={(v) => set({ states: v })}
          info="One state per line: label, energy, then optional degeneracy and properties. Paste columns from a spreadsheet; a header line is fine."
          enableMarkdown={false}
        />
      )}

      <Form.Dropdown id="unit" title="Energy unit" value={s.unit} onChange={(v) => set({ unit: v })}>
        <Form.Dropdown.Item value="kcal/mol" title="kcal/mol" />
        <Form.Dropdown.Item value="kJ/mol" title="kJ/mol" />
        <Form.Dropdown.Item value="eV" title="eV" />
        {!reaction && <Form.Dropdown.Item value="Eh" title="Hartree (absolute energies)" />}
      </Form.Dropdown>
      <Form.Dropdown
        id="temperature"
        title="Temperature"
        value={s.temperature}
        onChange={(v) => set({ temperature: v })}
      >
        {TEMPERATURE_PRESETS.map((t) => (
          <Form.Dropdown.Item key={t.value} value={t.value} title={`${t.title} · ${t.value} K`} />
        ))}
        <Form.Dropdown.Item value="custom" title="Other…" />
      </Form.Dropdown>
      {s.temperature === "custom" && (
        <Form.TextField
          id="customTemperature"
          title="Other temperature"
          placeholder="e.g. 250, 40 C, -20 °C"
          value={s.customTemperature}
          onChange={(v) => set({ customTemperature: v })}
        />
      )}

      {reaction && (
        <>
          <Form.Separator />
          <Form.Dropdown
            id="molecularity"
            title="Molecularity"
            value={s.molecularity}
            onChange={(v) => set({ molecularity: v as ProfileState["molecularity"] })}
          >
            <Form.Dropdown.Item value="unimolecular" title="Unimolecular (k in s⁻¹)" />
            <Form.Dropdown.Item value="bimolecular" title="Bimolecular A + B (k in M⁻¹ s⁻¹)" />
          </Form.Dropdown>
          {bimolecular && (
            <>
              <Form.Dropdown
                id="control"
                title="Control"
                value={s.control}
                onChange={(v) => set({ control: v as ProfileState["control"] })}
              >
                <Form.Dropdown.Item value="activation" title="Activation-controlled" />
                <Form.Dropdown.Item value="diffusion" title="Diffusion-limited (1/k = 1/k_act + 1/k_diff)" />
              </Form.Dropdown>
              {s.control === "diffusion" && (
                <Form.Dropdown id="solvent" title="Solvent" value={s.solvent} onChange={(v) => set({ solvent: v })}>
                  {solventChoices(tool.input_schema).map((c) => (
                    <Form.Dropdown.Item key={c.value} value={c.value} title={c.title} />
                  ))}
                </Form.Dropdown>
              )}
              {s.control === "diffusion" && s.solvent === "custom" && (
                <Form.TextField
                  id="viscosity"
                  title="Viscosity (mPa s)"
                  placeholder="e.g. 0.34"
                  value={s.viscosity}
                  onChange={(v) => set({ viscosity: v })}
                />
              )}
              <Form.TextField
                id="partner"
                title="Partner concentration (M)"
                placeholder="1"
                info="The other reactant B, for pseudo-first-order half-lives."
                value={s.partner}
                onChange={(v) => set({ partner: v })}
              />
              <Form.Dropdown
                id="standardState"
                title="Energies are for"
                value={s.standardState}
                onChange={(v) => set({ standardState: v })}
                info="Gas-phase calculations give 1 atm energies; they are converted to 1 M."
              >
                <Form.Dropdown.Item value="1 M" title="1 M (solution)" />
                <Form.Dropdown.Item value="1 atm" title="1 atm (gas-phase calculation)" />
              </Form.Dropdown>
            </>
          )}
          <Form.Separator />
          <Form.TextField
            id="targetHalfLife"
            title="Find temperature for t½"
            placeholder="optional, e.g. 1h, 30min"
            value={s.targetHalfLife}
            onChange={(v) => set({ targetHalfLife: v })}
          />
          <Form.TextField
            id="targetSelectivity"
            title="Find ΔΔG‡ for"
            placeholder="optional, e.g. 95:5, 90% ee, 10:1 dr"
            value={s.targetSelectivity}
            onChange={(v) => set({ targetSelectivity: v })}
          />
        </>
      )}
    </Form>
  );
}

function PathFields({
  index,
  row,
  state,
  onChange,
}: {
  index: number;
  row: PathRow;
  state: ProfileState;
  onChange: (patch: Partial<PathRow>) => void;
}) {
  const name = row.name.trim() || `P${index + 1}`;
  return (
    <>
      <Form.TextField
        id={`name-${index}`}
        title={`Path ${index + 1} · product`}
        placeholder={`P${index + 1}`}
        value={row.name}
        onChange={(v) => onChange({ name: v })}
      />
      <Form.TextField
        id={`ts-${index}`}
        title={`  TS → ${name}: ${tsFieldTitle(state)}`}
        placeholder={state.tsValues === "half-life" ? "e.g. 30min, 2h" : "e.g. 20.0"}
        value={row.ts}
        onChange={(v) => onChange({ ts: v })}
      />
      <Form.TextField
        id={`product-${index}`}
        title={`  ${name}: ${productFieldTitle(state)}`}
        placeholder={state.productValues === "equilibrium constant" ? "e.g. 150" : "e.g. -3.0"}
        value={row.product}
        onChange={(v) => onChange({ product: v })}
      />
    </>
  );
}
