# Se ejecuta DENTRO del contenedor kicad/kicad:9.0: abre cada tarjeta generada, la regraba en formato KiCad 9
import pcbnew, sys
for f in sys.argv[1:]:
    b = pcbnew.LoadBoard(f)
    ds = b.GetDesignSettings()
    ds.m_TrackMinWidth = pcbnew.FromMM(0.10 if "_A" in f else 0.127)
    ds.m_MinClearance = pcbnew.FromMM(0.10 if "_A" in f else 0.127)
    ds.m_ViasMinSize = pcbnew.FromMM(0.6); ds.m_MinThroughDrill = pcbnew.FromMM(0.3)
    ds.m_CopperEdgeClearance = pcbnew.FromMM(0.3)
    ds.m_HoleClearance = pcbnew.FromMM(0.2); ds.m_HoleToHoleMin = pcbnew.FromMM(0.25)
    nc = b.GetAllNetClasses()
    pcbnew.SaveBoard(f, b)
    print(f, "capas Cu:", b.GetCopperLayerCount(), "pistas:", len(b.GetTracks()), "huellas:", len(b.GetFootprints()),
          "bbox mm:", round(pcbnew.ToMM(b.GetBoardEdgesBoundingBox().GetWidth()),2), round(pcbnew.ToMM(b.GetBoardEdgesBoundingBox().GetHeight()),2))
