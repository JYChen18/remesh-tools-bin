#include <openvdb/openvdb.h>
#include <openvdb/tools/MeshToVolume.h>
#include <openvdb/tools/VolumeToMesh.h>

#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <cstddef>
#include <cstdlib>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

using Vec3d = std::array<double, 3>;
using Tri = std::array<int, 3>;

struct Mesh {
  std::vector<Vec3d> points;
  std::vector<Tri> triangles;
};

struct Bounds {
  double xmin = std::numeric_limits<double>::max();
  double xmax = -std::numeric_limits<double>::max();
  double ymin = std::numeric_limits<double>::max();
  double ymax = -std::numeric_limits<double>::max();
  double zmin = std::numeric_limits<double>::max();
  double zmax = -std::numeric_limits<double>::max();
};

struct Options {
  std::string input;
  std::string output;
  double resolution = 50.0;
  double level_set = 0.1;
  bool normalize = true;
};

void usage(std::ostream& os) {
  os << "Usage: OpenVDBSdfRemesh input.obj output.obj [options]\n"
     << "\n"
     << "Options:\n"
     << "  -r, --resolution value   preprocessing resolution (default: 50)\n"
     << "  -l, --level-set value    volumeToMesh level set value (default: 0.1)\n"
     << "      --no-normalize       apply OpenVDB directly in input coordinates\n"
     << "  -h, --help               show this help message\n";
}

double parse_double(std::string_view text, std::string_view name) {
  std::string value(text);
  char* end = nullptr;
  errno = 0;
  const double parsed = std::strtod(value.c_str(), &end);
  if (errno != 0 || end == value.c_str() || *end != '\0') {
    throw std::runtime_error("Invalid " + std::string(name) + ": " + value);
  }
  return parsed;
}

Options parse_args(int argc, char** argv) {
  Options options;
  std::vector<std::string> positional;

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "-h" || arg == "--help") {
      usage(std::cout);
      std::exit(0);
    }
    if (arg == "-r" || arg == "--resolution") {
      if (++i == argc) {
        throw std::runtime_error(arg + " requires a value");
      }
      options.resolution = parse_double(argv[i], "resolution");
      continue;
    }
    if (arg == "-l" || arg == "--level-set") {
      if (++i == argc) {
        throw std::runtime_error(arg + " requires a value");
      }
      options.level_set = parse_double(argv[i], "level-set");
      continue;
    }
    if (arg == "--no-normalize") {
      options.normalize = false;
      continue;
    }
    if (!arg.empty() && arg[0] == '-') {
      throw std::runtime_error("Unknown option: " + arg);
    }
    positional.push_back(arg);
  }

  if (positional.size() != 2) {
    usage(std::cerr);
    throw std::runtime_error("Expected input and output OBJ paths");
  }
  options.input = positional[0];
  options.output = positional[1];
  if (options.resolution <= 0.0) {
    throw std::runtime_error("resolution must be positive");
  }
  return options;
}

int parse_obj_index(std::string_view token, std::size_t point_count) {
  const std::size_t slash = token.find('/');
  token = token.substr(0, slash);
  if (token.empty()) {
    throw std::runtime_error("OBJ face has an empty vertex index");
  }

  int value = 0;
  const auto* begin = token.data();
  const auto* end = token.data() + token.size();
  const auto result = std::from_chars(begin, end, value);
  if (result.ec != std::errc() || result.ptr != end || value == 0) {
    throw std::runtime_error("Invalid OBJ face index: " + std::string(token));
  }

  const int index = value > 0 ? value - 1 : static_cast<int>(point_count) + value;
  if (index < 0 || static_cast<std::size_t>(index) >= point_count) {
    throw std::runtime_error("OBJ face index is out of range: " + std::string(token));
  }
  return index;
}

Mesh load_obj(const std::string& filename) {
  std::ifstream input(filename);
  if (!input) {
    throw std::runtime_error("Could not open input OBJ: " + filename);
  }

  Mesh mesh;
  std::string line;
  std::size_t line_number = 0;
  while (std::getline(input, line)) {
    ++line_number;
    if (line.empty() || line[0] == '#') {
      continue;
    }

    std::istringstream stream(line);
    std::string tag;
    stream >> tag;
    if (tag == "v") {
      Vec3d point{};
      if (!(stream >> point[0] >> point[1] >> point[2])) {
        throw std::runtime_error("Invalid OBJ vertex at line " + std::to_string(line_number));
      }
      mesh.points.push_back(point);
    } else if (tag == "f") {
      std::vector<int> indices;
      std::string token;
      while (stream >> token) {
        indices.push_back(parse_obj_index(token, mesh.points.size()));
      }
      if (indices.size() < 3) {
        throw std::runtime_error("OBJ face has fewer than 3 vertices at line " + std::to_string(line_number));
      }
      for (std::size_t i = 1; i + 1 < indices.size(); ++i) {
        mesh.triangles.push_back({indices[0], indices[i], indices[i + 1]});
      }
    }
  }

  if (mesh.points.empty()) {
    throw std::runtime_error("Input OBJ has no vertices: " + filename);
  }
  if (mesh.triangles.empty()) {
    throw std::runtime_error("Input OBJ has no faces: " + filename);
  }
  return mesh;
}

void save_obj(const std::string& filename, const Mesh& mesh) {
  std::ofstream output(filename);
  if (!output) {
    throw std::runtime_error("Could not open output OBJ: " + filename);
  }

  output << std::setprecision(17);
  for (const Vec3d& point : mesh.points) {
    output << "v " << point[0] << ' ' << point[1] << ' ' << point[2] << '\n';
  }
  for (const Tri& tri : mesh.triangles) {
    output << "f " << tri[0] + 1 << ' ' << tri[1] + 1 << ' ' << tri[2] + 1 << '\n';
  }
}

Bounds compute_bounds(const Mesh& mesh) {
  Bounds bounds;
  for (const Vec3d& point : mesh.points) {
    bounds.xmin = std::min(bounds.xmin, point[0]);
    bounds.xmax = std::max(bounds.xmax, point[0]);
    bounds.ymin = std::min(bounds.ymin, point[1]);
    bounds.ymax = std::max(bounds.ymax, point[1]);
    bounds.zmin = std::min(bounds.zmin, point[2]);
    bounds.zmax = std::max(bounds.zmax, point[2]);
  }
  return bounds;
}

double max_extent(const Bounds& bounds) {
  return std::max({bounds.xmax - bounds.xmin, bounds.ymax - bounds.ymin, bounds.zmax - bounds.zmin});
}

void normalize_mesh(Mesh& mesh, const Bounds& bounds) {
  const double extent = max_extent(bounds);
  if (extent <= 0.0) {
    throw std::runtime_error("Input OBJ has zero bounding-box extent");
  }

  const double xmid = 0.5 * (bounds.xmax + bounds.xmin);
  const double ymid = 0.5 * (bounds.ymax + bounds.ymin);
  const double zmid = 0.5 * (bounds.zmax + bounds.zmin);
  for (Vec3d& point : mesh.points) {
    point = {
      2.0 * (point[0] - xmid) / extent,
      2.0 * (point[1] - ymid) / extent,
      2.0 * (point[2] - zmid) / extent,
    };
  }
}

void recover_mesh(Mesh& mesh, const Bounds& bounds) {
  const double extent = max_extent(bounds);
  const double xmid = 0.5 * (bounds.xmax + bounds.xmin);
  const double ymid = 0.5 * (bounds.ymax + bounds.ymin);
  const double zmid = 0.5 * (bounds.zmax + bounds.zmin);
  for (Vec3d& point : mesh.points) {
    point = {
      point[0] * 0.5 * extent + xmid,
      point[1] * 0.5 * extent + ymid,
      point[2] * 0.5 * extent + zmid,
    };
  }
}

Mesh sdf_manifold(const Mesh& input, double resolution, double level_set) {
  std::vector<openvdb::Vec3s> points;
  std::vector<openvdb::Vec3I> triangles;
  std::vector<openvdb::Vec4I> quads;
  points.reserve(input.points.size());
  triangles.reserve(input.triangles.size());

  for (const Vec3d& point : input.points) {
    points.emplace_back(
      static_cast<float>(point[0] * resolution),
      static_cast<float>(point[1] * resolution),
      static_cast<float>(point[2] * resolution));
  }
  for (const Tri& tri : input.triangles) {
    triangles.emplace_back(tri[0], tri[1], tri[2]);
  }

  openvdb::math::Transform::Ptr transform = openvdb::math::Transform::createLinearTransform();
  openvdb::DoubleGrid::Ptr grid = openvdb::tools::meshToSignedDistanceField<openvdb::DoubleGrid>(
    *transform, points, triangles, quads, 3.0, 3.0);

  std::vector<openvdb::Vec3s> new_points;
  std::vector<openvdb::Vec3I> new_triangles;
  std::vector<openvdb::Vec4I> new_quads;
  openvdb::tools::volumeToMesh(*grid, new_points, new_triangles, new_quads, level_set);

  Mesh output;
  output.points.reserve(new_points.size());
  output.triangles.reserve(new_triangles.size() + 2 * new_quads.size());
  for (const openvdb::Vec3s& point : new_points) {
    output.points.push_back({point[0] / resolution, point[1] / resolution, point[2] / resolution});
  }
  for (const openvdb::Vec3I& tri : new_triangles) {
    output.triangles.push_back(
      {static_cast<int>(tri[0]), static_cast<int>(tri[2]), static_cast<int>(tri[1])});
  }
  for (const openvdb::Vec4I& quad : new_quads) {
    output.triangles.push_back(
      {static_cast<int>(quad[0]), static_cast<int>(quad[2]), static_cast<int>(quad[1])});
    output.triangles.push_back(
      {static_cast<int>(quad[0]), static_cast<int>(quad[3]), static_cast<int>(quad[2])});
  }
  return output;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parse_args(argc, argv);
    openvdb::initialize();

    Mesh input = load_obj(options.input);
    const Bounds bounds = compute_bounds(input);
    if (options.normalize) {
      normalize_mesh(input, bounds);
    }

    Mesh output = sdf_manifold(input, options.resolution, options.level_set);
    if (options.normalize) {
      recover_mesh(output, bounds);
    }
    save_obj(options.output, output);

    std::cerr << "OpenVDBSdfRemesh: " << input.points.size() << " vertices, " << input.triangles.size()
              << " triangles -> " << output.points.size() << " vertices, " << output.triangles.size()
              << " triangles\n";
    return 0;
  } catch (const std::exception& exc) {
    std::cerr << "OpenVDBSdfRemesh: error: " << exc.what() << '\n';
    return 1;
  }
}
