import { Action, ActionPanel, Color, Detail, Grid, Icon, Keyboard, List, open, showToast, Toast } from "@raycast/api";
import { useCachedPromise } from "@raycast/utils";
import { useMemo, useState } from "react";
import { getTransport } from "../connection";
import {
  type AminoAcid,
  type AminoAcidData,
  CLASS_COLORS,
  isAminoAcidData,
  links,
  num,
  pkaText,
  search,
  sections,
  signed,
  SORT_TITLES,
  type SortMode,
  stereoText,
} from "../lib/aminoacids";
import type { ToolInfo } from "../lib/contract";
import { writeImage } from "../lib/images";
import { ErrorView } from "./ErrorView";
import { ResultView } from "./ResultView";

// Amino Acids (BIO-01): on the left, every amino acid by name and codes, grouped by
// side-chain class, to scan and scroll quickly; on the right, the selected one's
// structure card and key values. The dropdown changes the order. Enter opens the
// full page; cmd-G shows all structures as a grid; cmd-O opens the rotating 3D view
// in the browser (Raycast cannot rotate 3D in place).

const AA_TOOL: ToolInfo = {
  id: "BIO-01",
  name: "aa",
  title: "Amino acids",
  summary: "The 20 (+2) amino acids: codes, 2D and 3D structures, classes, masses, pKa, codons",
  category: "biochemistry",
  keywords: [],
  resources: "light",
  requires: [],
  available: true,
  unavailable_reason: "",
  icon: "",
  start_view: "All amino acids",
  input_schema: {},
};

const OPEN_3D: Keyboard.Shortcut = { modifiers: ["cmd"], key: "o" };
const FULL_CARD: Keyboard.Shortcut = { modifiers: ["cmd"], key: "i" };
const SHOW_GRID: Keyboard.Shortcut = { modifiers: ["cmd"], key: "g" };

// Part of the cache key: raise it when the shape of the tool's data changes, so a
// list cached by an older version is not shown with the new code.
const DATA_FORMAT = 3; // 2: one card drawing per amino acid (was light + dark); 3: + banners

// eslint-disable-next-line @typescript-eslint/no-unused-vars
async function loadData(format: number): Promise<AminoAcidData> {
  const response = await getTransport().run("aa", {}, { record: false });
  if (!response.ok) throw response.error; // ErrorInfo: shown by ErrorView
  return response.result.data as unknown as AminoAcidData;
}

type Images = Record<string, string>; // one-letter code -> SVG file (square card)
type Banners = Record<string, string>; // one-letter code -> SVG file (wide card)

// The drawings come as SVG text (so they can be cached); Raycast needs files.
function useImages(data: AminoAcidData | undefined): Images {
  return useMemo(() => {
    if (!data) return {};
    return Object.fromEntries(Object.entries(data.drawings).map(([one, svg]) => [one, writeImage(svg, `aa-${one}`)]));
  }, [data]);
}

async function open3D(a: AminoAcid) {
  const toast = await showToast({ style: Toast.Style.Animated, title: `Opening ${a.name} in 3D…` });
  try {
    const response = await getTransport().run("aa", { query: a.one }, { record: false });
    if (!response.ok) throw new Error(response.error.message);
    const viewer = response.result.artifacts.find((x) => x.kind === "html")?.path;
    if (!viewer) throw new Error("csk returned no 3D viewer.");
    await open(viewer);
    await toast.hide();
  } catch (e) {
    toast.style = Toast.Style.Failure;
    toast.title = "Could not open the 3D view";
    toast.message = e instanceof Error ? e.message : String(e);
  }
}

function AminoAcidActions({
  a,
  images,
  withPage,
  grid,
}: {
  a: AminoAcid;
  images: Images;
  withPage: boolean;
  grid?: React.ReactNode; // "Show as Grid" target, from the list
}) {
  return (
    <>
      {withPage && <Action.Push title="Open" icon={Icon.Document} target={<AminoAcidDetail a={a} images={images} />} />}
      {grid && <Action.Push title="Show as Grid" icon={Icon.AppWindowGrid3x3} shortcut={SHOW_GRID} target={grid} />}
      <Action title="Open 3D View in Browser" icon={Icon.Globe} shortcut={OPEN_3D} onAction={() => open3D(a)} />
      <Action.Push
        title="Show Full Card"
        icon={Icon.List}
        shortcut={FULL_CARD}
        target={<ResultView tool={AA_TOOL} input={{ query: a.one }} options={{ record: false }} />}
      />
      <ActionPanel.Section title="Copy">
        <Action.CopyToClipboard title={`Copy One-Letter Code (${a.one})`} content={a.one} />
        <Action.CopyToClipboard title={`Copy Three-Letter Code (${a.three})`} content={a.three} />
        <Action.CopyToClipboard
          title="Copy Residue Mass (Monoisotopic)"
          content={num(a.mass.residue_mono, 5)}
          shortcut={Keyboard.Shortcut.Common.Copy}
        />
        <Action.CopyToClipboard title="Copy Residue Mass (Average)" content={num(a.mass.residue_avg, 2)} />
        <Action.CopyToClipboard title="Copy SMILES" content={a.smiles} />
      </ActionPanel.Section>
    </>
  );
}

export function AminoAcidDetail({ a, images }: { a: AminoAcid; images: Images }) {
  const image = images[a.one];
  const markdown = [
    `# ${a.name} · ${a.three} · ${a.one}`,
    "",
    image ? `![${a.name}](${encodeURI(image)}?raycast-width=300&raycast-height=300)` : "",
    "",
    `_pH 7 form; side chain highlighted. ${a.pka.status === "provisional" ? "pKa and pI are provisional (one textbook table)." : ""}_`,
    ...(a.codons_note ? ["", `_${a.codons_note}_`] : []),
  ].join("\n");
  const color = CLASS_COLORS[a.class];
  return (
    <Detail
      navigationTitle={a.name}
      markdown={markdown}
      metadata={
        <Detail.Metadata>
          <Detail.Metadata.TagList title="Class">
            <Detail.Metadata.TagList.Item text={a.class_title} color={color} />
            {a.essential && <Detail.Metadata.TagList.Item text="essential" />}
          </Detail.Metadata.TagList>
          <Detail.Metadata.Label title="Codes" text={`${a.one} · ${a.three}`} />
          <Detail.Metadata.Label title="Formula" text={a.formula} />
          <Detail.Metadata.Label title="Stereo" text={stereoText(a)} />
          <Detail.Metadata.Separator />
          <Detail.Metadata.Label title="Residue mass (mono)" text={`${num(a.mass.residue_mono, 5)} u`} />
          <Detail.Metadata.Label title="Residue mass (avg)" text={`${num(a.mass.residue_avg, 2)} g/mol`} />
          <Detail.Metadata.Label title="Molecular mass (mono)" text={`${num(a.mass.mono, 5)} u`} />
          <Detail.Metadata.Separator />
          <Detail.Metadata.Label
            title={a.pka.side_chain !== null ? "pKa (COOH · NH₃⁺ · side chain)" : "pKa (COOH · NH₃⁺)"}
            text={pkaText(a)}
          />
          <Detail.Metadata.Label title="pI" text={num(a.pi, 2)} />
          <Detail.Metadata.Label title="Hydropathy (Kyte–Doolittle)" text={signed(a.hydropathy_kd)} />
          <Detail.Metadata.Label title="Codons" text={a.codons.join(", ") || "—"} />
          <Detail.Metadata.Separator />
          {links(a).map((l) => (
            <Detail.Metadata.Link key={l.title} title={l.title} text={l.text} target={l.url} />
          ))}
        </Detail.Metadata>
      }
      actions={
        <ActionPanel>
          <AminoAcidActions a={a} images={images} withPage={false} />
        </ActionPanel>
      }
    />
  );
}

type Found = ReturnType<typeof search>;

function useBanners(data: AminoAcidData | undefined): Banners {
  return useMemo(() => {
    if (!data) return {};
    return Object.fromEntries(
      Object.entries(data.banners).map(([one, svg]) => [one, writeImage(svg, `aa-${one}-wide`)]),
    );
  }, [data]);
}

function useAminoAcids() {
  const cached = useCachedPromise(loadData, [DATA_FORMAT], { keepPreviousData: true });
  const data = isAminoAcidData(cached.data) ? cached.data : undefined;
  return { ...cached, data, images: useImages(data), banners: useBanners(data) };
}

// The groups to show: the sections of the chosen order, or one section of search results.
function groups(
  data: AminoAcidData,
  mode: SortMode,
  found: Found,
): { title: string; subtitle: string; items: AminoAcid[] }[] {
  if (found.matches === null) return sections(data, mode);
  if (!found.matches.length) return [];
  return [
    {
      title: found.ambiguous ? `${found.ambiguous.one} · ${found.ambiguous.three}` : "Results",
      subtitle: found.ambiguous ? found.ambiguous.meaning : String(found.matches.length),
      items: found.matches,
    },
  ];
}

const EMPTY_HINT = "Try a one-letter code (W), a three-letter code (Trp), a name, or a class (aromatic).";

function OrderDropdown({ mode, setMode, grid }: { mode: SortMode; setMode: (m: SortMode) => void; grid?: boolean }) {
  const Dropdown = grid ? Grid.Dropdown : List.Dropdown;
  return (
    <Dropdown tooltip="Order" storeValue value={mode} onChange={(v) => setMode(v as SortMode)}>
      {(Object.keys(SORT_TITLES) as SortMode[]).map((m) => (
        <Dropdown.Item key={m} title={SORT_TITLES[m]} value={m} />
      ))}
    </Dropdown>
  );
}

// Right-hand panel of the list: the structure card and the values most often needed.
// The banner is a wide white card (520 × 210), so it spans the top of the panel.
const BANNER_HEIGHT = 160; // px in the panel: leaves room for the values below

function SideDetail({ a, banners }: { a: AminoAcid; banners: Banners }) {
  const image = banners[a.one];
  const markdown = image ? `![${a.name}](${encodeURI(image)}?raycast-height=${BANNER_HEIGHT})` : `# ${a.name}`;
  return (
    <List.Item.Detail
      markdown={markdown}
      metadata={
        <List.Item.Detail.Metadata>
          <List.Item.Detail.Metadata.Label title={a.name} text={`${a.three} · ${a.one}`} />
          <List.Item.Detail.Metadata.TagList title="Class">
            <List.Item.Detail.Metadata.TagList.Item text={a.class_title} color={CLASS_COLORS[a.class]} />
            {a.essential && <List.Item.Detail.Metadata.TagList.Item text="essential" />}
          </List.Item.Detail.Metadata.TagList>
          <List.Item.Detail.Metadata.Label title="Formula" text={a.formula} />
          <List.Item.Detail.Metadata.Label title="Residue mass (mono)" text={`${num(a.mass.residue_mono, 5)} u`} />
          <List.Item.Detail.Metadata.Label title="Residue mass (avg)" text={`${num(a.mass.residue_avg, 2)} g/mol`} />
          <List.Item.Detail.Metadata.Label title="pI (provisional)" text={num(a.pi, 2)} />
          <List.Item.Detail.Metadata.Label title="Hydropathy (Kyte–Doolittle)" text={signed(a.hydropathy_kd)} />
          <List.Item.Detail.Metadata.Label title="Codons" text={a.codons.join(", ") || "—"} />
        </List.Item.Detail.Metadata>
      }
    />
  );
}

export function AminoAcidsView({ initialSearch = "" }: { initialSearch?: string }) {
  const { data, images, banners, isLoading, error, revalidate } = useAminoAcids();
  const [searchText, setSearchText] = useState(initialSearch);
  const [mode, setMode] = useState<SortMode>("class");
  if (error && !data) return <ErrorView error={error} onRetry={revalidate} />;
  const found: Found = data ? search(data, searchText) : { matches: null };
  return (
    <List
      navigationTitle="Amino Acids"
      isLoading={isLoading}
      isShowingDetail
      filtering={false}
      searchText={searchText}
      onSearchTextChange={setSearchText}
      searchBarPlaceholder="W, Trp, tryptophan, aromatic, B…"
      searchBarAccessory={<OrderDropdown mode={mode} setMode={setMode} />}
    >
      {data &&
        groups(data, mode, found).map((g) => (
          <List.Section key={g.title} title={g.title} subtitle={g.subtitle}>
            {g.items.map((a) => (
              <List.Item
                key={a.one}
                id={a.one}
                icon={{ source: Icon.CircleFilled, tintColor: CLASS_COLORS[a.class] ?? Color.SecondaryText }}
                title={a.name}
                subtitle={`${a.three} · ${a.one}`}
                detail={<SideDetail a={a} banners={banners} />}
                actions={
                  <ActionPanel>
                    <AminoAcidActions a={a} images={images} withPage grid={<AminoAcidsGrid initialMode={mode} />} />
                  </ActionPanel>
                }
              />
            ))}
          </List.Section>
        ))}
      {data && found.matches !== null && found.matches.length === 0 && (
        <List.EmptyView icon={Icon.MagnifyingGlass} title="No amino acid found" description={EMPTY_HINT} />
      )}
    </List>
  );
}

// All structures as cards (cmd-G from the list): each card fills its tile.
export function AminoAcidsGrid({ initialMode = "class" }: { initialMode?: SortMode }) {
  const { data, images, isLoading, error, revalidate } = useAminoAcids();
  const [searchText, setSearchText] = useState("");
  const [mode, setMode] = useState<SortMode>(initialMode);
  if (error && !data) return <ErrorView error={error} onRetry={revalidate} />;
  const found: Found = data ? search(data, searchText) : { matches: null };
  return (
    <Grid
      navigationTitle="Amino Acids"
      isLoading={isLoading}
      columns={6}
      aspectRatio="1"
      fit={Grid.Fit.Fill}
      inset={Grid.Inset.Zero}
      filtering={false}
      searchText={searchText}
      onSearchTextChange={setSearchText}
      searchBarPlaceholder="W, Trp, tryptophan, aromatic, B…"
      searchBarAccessory={<OrderDropdown mode={mode} setMode={setMode} grid />}
    >
      {data &&
        groups(data, mode, found).map((g) => (
          <Grid.Section key={g.title} title={g.title} subtitle={g.subtitle}>
            {g.items.map((a) => (
              <Grid.Item
                key={a.one}
                id={a.one}
                content={images[a.one] ? { source: images[a.one] } : Icon.Circle}
                title={`${a.three} · ${a.one}`}
                subtitle={a.name}
                actions={
                  <ActionPanel>
                    <AminoAcidActions a={a} images={images} withPage />
                  </ActionPanel>
                }
              />
            ))}
          </Grid.Section>
        ))}
      {data && found.matches !== null && found.matches.length === 0 && (
        <Grid.EmptyView icon={Icon.MagnifyingGlass} title="No amino acid found" description={EMPTY_HINT} />
      )}
    </Grid>
  );
}
