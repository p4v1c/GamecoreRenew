// Reads files the way RPCS3 v0.0.41 does (bin_patch.cpp load_config / load,
// cfg::node decode), with the yaml-cpp RPCS3 ships. Prints a canonical dump.
#include <yaml-cpp/yaml.h>
#include <iostream>
#include <fstream>
#include <sstream>
#include <regex>
static void dump(const YAML::Node& n, const std::string& path) {
  if (n.IsMap()) { for (auto p : n) dump(p.second, path + "/" + p.first.Scalar()); }
  else if (n.IsSequence()) { std::cout << path << " = [seq " << n.size() << "]\n"; }
  else if (n.IsScalar()) { std::cout << path << " = " << n.Scalar() << "\n"; }
}
int main(int argc, char** argv) {
  std::string mode = argv[1];
  std::ifstream f(argv[2]); std::stringstream ss; ss << f.rdbuf();
  YAML::Node root;
  try { root = YAML::Load(ss.str()); } catch (const std::exception& e) { std::cout << "PARSE-ERROR " << e.what() << "\n"; return 2; }
  if (mode == "config") { dump(root, ""); return 0; }
  if (mode == "patchconfig") {
    // bin_patch.cpp patch_engine::load_config
    for (const auto pair : root) {
      const std::string& hash = pair.first.Scalar();
      if (!pair.second.IsMap()) { std::cout << "ERR expected map " << hash << "\n"; continue; }
      for (const auto patch : pair.second) for (const auto t : patch.second) for (const auto s : t.second) for (const auto v : s.second) {
        bool enabled = false;
        if (v.second.IsMap()) { if (const auto e = v.second["Enabled"]) enabled = e.as<bool>(false); }
        else enabled = v.second.as<bool>(false);
        std::cout << hash << "|" << patch.first.Scalar() << "|" << t.first.Scalar() << "|" << s.first.Scalar() << "|" << v.first.Scalar() << "|" << (enabled ? "on" : "off") << "\n";
      }
    }
    return 0;
  }
  if (mode == "patchfile") {
    // bin_patch.cpp patch_engine::load: Games/<title>/<serial>: [versions] ; version regex
    static const std::regex app_ver("^([0-9]{2}\\.[0-9]{2})$");
    std::string want = argc > 3 ? argv[3] : "";
    for (const auto pair : root) {
      const std::string& key = pair.first.Scalar();
      if (key == "Version" || key == "Anchors" || !pair.second.IsMap()) continue;
      if (!want.empty() && key != want) continue;
      for (const auto p : pair.second) {
        auto g = p.second["Games"];
        if (!g || !g.IsMap()) continue;
        for (const auto t : g) for (const auto s : t.second) {
          if (!s.second.IsSequence()) continue;
          for (const auto v : s.second) {
            std::string ver = v.Scalar();
            bool ok = ver == "All" || std::regex_match(ver, app_ver);
            std::cout << key << "|" << p.first.Scalar() << "|" << t.first.Scalar() << "|" << s.first.Scalar() << "|" << ver << (ok ? "" : " (INVALID)") << "|ops=" << (p.second["Patch"] ? p.second["Patch"].size() : 0) << "|pv=" << (p.second["Patch Version"] ? p.second["Patch Version"].Scalar() : "") << "\n";
          }
        }
      }
    }
    return 0;
  }
  return 1;
}
