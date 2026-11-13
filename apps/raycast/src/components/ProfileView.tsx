// Energy Profile (ENE-01) in two columns: the paths on the left, the drawing and
// the answer on the right, redrawn as values change. Type "D 21 -4" (name, TS,
// product) in the search bar and press Enter to add a path; the drawing on the
// right already shows it while you type. Enter on a path edits it. Reaction or
// populations beside the search bar; temperature (typed, in K) and unit in the
// list, the rest under "More options". The last input is remembered.
import { Action, ActionPanel, Form, Icon, Keyboard, List, useNavigation } from "@raycast/api";
import { useCachedPromise, useCachedState } from "@raycast/utils";
import { type ReactNode, useState } from "react";
import { getTransport } from "../connection";
import type { RunResponse, ToolInfo } from "../lib/contract";
import { errorText } from "../lib/error-text";
import {
  EXAMPLE_STATE,
  MAX_PATHS,
  MAX_STATES,
  optionsSummary,
  panelMarkdown,
  type PathRow,
  pathSubtitle,
  productLabel,
  profileInput,
  type ProfileState,
  solventChoices,
  stateSubtitle,
  type StateRow,
  temperatureTitle,
  tsLabel,
  unitChoices,
  withTyped,
} from "../lib/profile";
import { ErrorView } from "./ErrorView";
import { ResultView } from "./ResultView";
import { useToolInfo } from "./use-tool";

const PANEL_WIDTH = 460; // px: the drawing in the right-hand panel
const FULL_WIDTH = 640; // px: the drawing on the full result page
const SHOW_FULL: Keyboard.Shortcut = { modifiers: ["cmd"], key: "return" };
const RESET: Keyboard.Shortcut = { modifiers: ["cmd", "shift"], key: "r" };

export function ProfileCommand() {
  const { tool, error, revalidate } = useToolInfo("profile");
  if (error) return <ErrorView error={error} onRetry={revalidate} />;
  if (!tool) return <List isLoading searchBarPlaceholder="Starting…" />;
  return <ProfileView tool={tool} />;
}

// Shared by every screen of this command (the cache keeps them in step).
function useProfile() {
  const [s, setS] = useCachedState<ProfileState>("profile-view-2", EXAMPLE_STATE);
  return { s, set: (patch: Partial<ProfileState>) => setS({ ...s, ...patch }), reset: () => setS(EXAMPLE_STATE) };
}

type Preview = { kind: "ok"; response: RunResponse } | { kind: "input"; message: string };

async function preview(inputJson: string): Promise<Preview> {
  const response = await getTransport().run("profile", JSON.parse(inputJson), { record: false });
  if (response.ok) return { kind: "ok", response };
  // An input the tool cannot use yet (e.g. a TS below its product): say why, keep typing.
  if (response.error.type === "input") return { kind: "input", message: response.error.message };
  throw response.error;
}

export function ProfileView({ tool }: { tool: ToolInfo }) {
  const { push, pop } = useNavigation();
  const { s, set, reset } = useProfile();
  const [text, setText] = useState("");
  const reaction = s.mode === "reaction";
  const typed = text.trim() ? withTyped(s, text) : null;
  // The drawing shows what is typed before Enter adds it.
  const shown = typed ?? s;
  const input = profileInput(shown);
  const { data, isLoading, error } = useCachedPromise(preview, [JSON.stringify(input)], { keepPreviousData: true });

  const detail = <Panel data={data} error={error} />;
  const full = () => push(<ResultView tool={tool} input={profileInput(s)} drawingWidth={FULL_WIDTH} onEdit={pop} />);
  const add = () => {
    if (!typed) return;
    set(reaction ? { paths: typed.paths } : { states: typed.states });
    setText("");
  };

  // Actions on every row.
  const canAdd = reaction ? s.paths.length < MAX_PATHS : s.states.length < MAX_STATES;
  const addTarget = reaction ? <PathForm index={-1} /> : <StateForm index={-1} />;
  const addTitle = reaction ? "Add Path" : "Add State";
  const common = (
    <>
      <Action title="Show Full Result" icon={Icon.Document} shortcut={SHOW_FULL} onAction={full} />
      {canAdd && (
        <Action.Push title={addTitle} icon={Icon.Plus} shortcut={Keyboard.Shortcut.Common.New} target={addTarget} />
      )}
      {data?.kind === "ok" && (
        <Action.CopyToClipboard
          title="Copy Answer"
          content={data.response.result.answer}
          shortcut={Keyboard.Shortcut.Common.Copy}
        />
      )}
      {reaction && (
        <Action.Push
          title="More Options"
          icon={Icon.Gear}
          shortcut={{ modifiers: ["cmd", "shift"], key: "p" }}
          target={<OptionsForm tool={tool} />}
        />
      )}
      <Action title="Reset to Example" icon={Icon.ArrowCounterClockwise} shortcut={RESET} onAction={reset} />
    </>
  );

  const rows: ReactNode[] = reaction
    ? s.paths.map((p, i) => (
        <List.Item
          key={`path-${i}`}
          icon={Icon.ArrowRight}
          title={p.name || `P${i + 1}`}
          subtitle={pathSubtitle(s, p)}
          detail={detail}
          actions={
            <ActionPanel>
              <Action.Push title="Edit Path" icon={Icon.Pencil} target={<PathForm index={i} />} />
              {common}
              <Action
                title="Remove Path"
                icon={Icon.Trash}
                style={Action.Style.Destructive}
                shortcut={Keyboard.Shortcut.Common.Remove}
                onAction={() => set({ paths: s.paths.filter((_, j) => j !== i) })}
              />
            </ActionPanel>
          }
        />
      ))
    : s.states.map((r, i) => (
        <List.Item
          key={`state-${i}`}
          icon={Icon.Circle}
          title={r.name || `s${i + 1}`}
          subtitle={stateSubtitle(r, s.unit)}
          detail={detail}
          actions={
            <ActionPanel>
              <Action.Push title="Edit State" icon={Icon.Pencil} target={<StateForm index={i} />} />
              {common}
              <Action
                title="Remove State"
                icon={Icon.Trash}
                style={Action.Style.Destructive}
                shortcut={Keyboard.Shortcut.Common.Remove}
                onAction={() => set({ states: s.states.filter((_, j) => j !== i) })}
              />
            </ActionPanel>
          }
        />
      ));

  const placeholder = reaction
    ? `Add a path: name  ${tsLabel(s)}  ${productLabel(s)}   e.g. D 21 -4`
    : `Add a state: name  energy (${s.unit})  [degeneracy]   e.g. conf4 1.2`;
  const atMax = reaction && s.paths.length >= MAX_PATHS;

  return (
    <List
      navigationTitle="Energy Profile"
      isShowingDetail
      filtering={false}
      throttle
      isLoading={isLoading}
      searchText={text}
      onSearchTextChange={setText}
      searchBarPlaceholder={placeholder}
      searchBarAccessory={
        <List.Dropdown
          tooltip="Mode"
          value={s.mode}
          onChange={(v) =>
            v !== s.mode &&
            set({ mode: v as ProfileState["mode"], unit: v === "reaction" && s.unit === "Eh" ? "kcal/mol" : s.unit })
          }
        >
          <List.Dropdown.Item value="reaction" title="Reaction (kinetics)" icon={Icon.ArrowRight} />
          <List.Dropdown.Item value="populations" title="Populations (Boltzmann)" icon={Icon.BarChart} />
        </List.Dropdown>
      }
    >
      {text.trim() && (
        <List.Section title="Add">
          <List.Item
            icon={typed ? Icon.Plus : Icon.QuestionMarkCircle}
            title={typed ? `Add ${text.trim()}` : atMax ? `At most ${MAX_PATHS} paths` : "Not read yet"}
            subtitle={
              typed
                ? "Enter adds it; the drawing already shows it"
                : reaction
                  ? "name, then TS and product values; - for unknown; ; between paths"
                  : "name, energy, optional degeneracy; ; between states"
            }
            detail={detail}
            actions={
              <ActionPanel>
                {typed && <Action title="Add" icon={Icon.Plus} onAction={add} />}
                {common}
              </ActionPanel>
            }
          />
        </List.Section>
      )}
      <List.Section
        title={reaction ? "Paths from A (0)" : "States"}
        subtitle={reaction ? `${s.paths.length} of ${MAX_PATHS}` : `${s.states.length}`}
      >
        {rows}
        {canAdd && (
          <List.Item
            icon={Icon.Plus}
            title={addTitle}
            subtitle={reaction ? "or type D 21 -4 above" : "or type conf4 1.2 above"}
            detail={detail}
            actions={
              <ActionPanel>
                <Action.Push title={addTitle} icon={Icon.Plus} target={addTarget} />
                {common}
              </ActionPanel>
            }
          />
        )}
      </List.Section>
      <List.Section title="Settings">
        <List.Item
          icon={Icon.Temperature}
          title="Temperature"
          subtitle={temperatureTitle(s)}
          detail={detail}
          actions={
            <ActionPanel>
              <Action.Push title="Set Temperature" icon={Icon.Temperature} target={<TemperatureForm />} />
              {common}
            </ActionPanel>
          }
        />
        <List.Item
          icon={Icon.Ruler}
          title="Energy unit"
          subtitle={s.unit}
          detail={detail}
          actions={
            <ActionPanel>
              <Action.Push title="Choose Unit" icon={Icon.Ruler} target={<UnitPicker />} />
              {common}
            </ActionPanel>
          }
        />
        {reaction && (
          <List.Item
            icon={Icon.Gear}
            title="More options"
            subtitle={optionsSummary(s) || "molecularity, diffusion, k or t½ input, targets"}
            detail={detail}
            actions={
              <ActionPanel>
                <Action.Push title="More Options" icon={Icon.Gear} target={<OptionsForm tool={tool} />} />
                {common}
              </ActionPanel>
            }
          />
        )}
      </List.Section>
    </List>
  );
}

// The right-hand panel: the drawing, then the answer and the key values as text
// (no metadata column, so the drawing gets the room).
function Panel({ data, error }: { data?: Preview; error?: unknown }) {
  if (error) return <List.Item.Detail markdown={errorText(error).markdown} />;
  if (!data) return <List.Item.Detail isLoading markdown="" />;
  if (data.kind === "input") return <List.Item.Detail markdown={`**Not drawn yet**\n\n${data.message}`} />;
  const { result } = data.response;
  return <List.Item.Detail markdown={panelMarkdown(result, PANEL_WIDTH)} />;
}

function UnitPicker() {
  const { pop } = useNavigation();
  const { s, set } = useProfile();
  return (
    <List navigationTitle="Energy Unit">
      {unitChoices(s.mode).map((u) => (
        <List.Item
          key={u.value}
          title={u.title}
          icon={u.value === s.unit ? Icon.CheckCircle : Icon.Circle}
          actions={
            <ActionPanel>
              <Action
                title="Choose"
                icon={Icon.Check}
                onAction={() => {
                  set({ unit: u.value });
                  pop();
                }}
              />
            </ActionPanel>
          }
        />
      ))}
    </List>
  );
}

function PathForm({ index }: { index: number }) {
  const { pop } = useNavigation();
  const { s, set } = useProfile();
  // index -1: a new path, added after the others.
  const [row, setRow] = useState<PathRow>(s.paths[index] ?? { name: `P${s.paths.length + 1}`, ts: "", product: "" });
  const save = () => {
    set({ paths: index < 0 ? [...s.paths, row] : s.paths.map((p, j) => (j === index ? row : p)) });
    pop();
  };
  return (
    <Form
      navigationTitle={index < 0 ? "New Path" : `Path ${index + 1}`}
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Save" icon={Icon.Check} onSubmit={save} />
        </ActionPanel>
      }
    >
      <Form.TextField id="name" title="Product" value={row.name} onChange={(v) => setRow({ ...row, name: v })} />
      <Form.TextField
        id="ts"
        title={tsLabel(s)}
        placeholder={s.tsValues === "half-life" ? "e.g. 30min, 2h" : "empty if unknown"}
        value={row.ts}
        onChange={(v) => setRow({ ...row, ts: v })}
      />
      <Form.TextField
        id="product"
        title={productLabel(s)}
        placeholder="empty if unknown"
        value={row.product}
        onChange={(v) => setRow({ ...row, product: v })}
      />
    </Form>
  );
}

function StateForm({ index }: { index: number }) {
  const { pop } = useNavigation();
  const { s, set } = useProfile();
  // index -1: a new state, added after the others.
  const [row, setRow] = useState<StateRow>(
    s.states[index] ?? { name: `conf${s.states.length + 1}`, energy: "", degeneracy: "" },
  );
  const save = () => {
    set({ states: index < 0 ? [...s.states, row] : s.states.map((r, j) => (j === index ? row : r)) });
    pop();
  };
  return (
    <Form
      navigationTitle={index < 0 ? "New State" : `State ${index + 1}`}
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Save" icon={Icon.Check} onSubmit={save} />
        </ActionPanel>
      }
    >
      <Form.TextField id="name" title="Name" value={row.name} onChange={(v) => setRow({ ...row, name: v })} />
      <Form.TextField
        id="energy"
        title={`Energy (${s.unit})`}
        value={row.energy}
        onChange={(v) => setRow({ ...row, energy: v })}
      />
      <Form.TextField
        id="degeneracy"
        title="Degeneracy"
        placeholder="1"
        value={row.degeneracy}
        onChange={(v) => setRow({ ...row, degeneracy: v })}
      />
    </Form>
  );
}

function TemperatureForm() {
  const { pop } = useNavigation();
  const { s, set } = useProfile();
  const [t, setT] = useState(s.temperature);
  return (
    <Form
      navigationTitle="Temperature"
      actions={
        <ActionPanel>
          <Action.SubmitForm
            title="Save"
            icon={Icon.Check}
            onSubmit={() => {
              set({ temperature: t.trim() || "298.15" });
              pop();
            }}
          />
        </ActionPanel>
      }
    >
      <Form.TextField
        id="temperature"
        title="Temperature (K)"
        placeholder="298.15"
        info="A number is in kelvin. With a unit: 40 C, -78 °C."
        value={t}
        onChange={setT}
      />
    </Form>
  );
}

// Reaction options besides the energies, unit and temperature. Changes apply at once.
function OptionsForm({ tool }: { tool: ToolInfo }) {
  const { pop } = useNavigation();
  const { s, set } = useProfile();
  const reaction = s.mode === "reaction";
  const bimolecular = s.molecularity === "bimolecular";
  return (
    <Form
      navigationTitle="More Options"
      actions={
        <ActionPanel>
          <Action title="Done" icon={Icon.Check} onAction={pop} />
        </ActionPanel>
      }
    >
      {reaction && (
        <>
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
