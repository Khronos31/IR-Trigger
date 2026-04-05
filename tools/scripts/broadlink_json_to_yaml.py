import argparse
import json
import yaml

def convert_json_to_yaml(input_file: str, output_file: str, domain: str = "climate"):
    """Convert a simple JSON dictionary of base64 codes to IR-Trigger YAML format."""
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file {input_file}: {e}")
        return

    buttons = {}
    for key, value in data.items():
        if isinstance(value, str):
            buttons[key] = f"B64-{value}"

    yaml_dict = {
        "domain": domain,
        "mapping": {},
        "buttons": buttons
    }

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            yaml.dump(yaml_dict, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        print(f"Successfully converted {input_file} to {output_file}")
    except Exception as e:
        print(f"Error writing YAML file {output_file}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Broadlink Base64 JSON dict to IR-Trigger YAML template.")
    parser.add_argument("input", help="Path to input JSON file")
    parser.add_argument("output", help="Path to output YAML file")
    parser.add_argument("--domain", default="climate", help="Domain to set in the generated YAML (default: climate)")
    
    args = parser.parse_args()
    convert_json_to_yaml(args.input, args.output, args.domain)
