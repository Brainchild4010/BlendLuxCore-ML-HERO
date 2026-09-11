import bpy
from bpy.props import FloatProperty, BoolProperty, EnumProperty
from ..base import LuxCoreNodeMaterial
from ..sockets import LuxCoreSocketFloat
from ...utils.node import get_active_output
from ... import icons
from ...utils import node as utils_node
from ...utils.node import Roughness, ThinFilmCoating

CAUCHYB_DESCRIPTION = (
    "Dispersion strength (cauchy B coefficient)\n"
    "Realistic values range from 0.00354 to 0.01342\n"
    "Supported by ML HERO RoughGlass; not supported by architectural glass"
)

DISPERSION_MODEL_ITEMS = (
    ("CAUCHY", "Cauchy", "Use the existing Cauchy dispersion model"),
    ("SELLMEIER", "Sellmeier", "Use a physical Sellmeier dispersion curve from an optical-glass preset"),
)

SELLMEIER_PRESET_ITEMS = (
    ("N_BK7", "N-BK7", "Schott N-BK7 optical crown glass"),
    ("FUSED_SILICA", "Fused Silica", "Fused silica / synthetic quartz"),
    ("SF10", "SF10", "Schott SF10 dense flint glass"),
    ("SF11", "SF11", "Schott SF11 dense flint glass with strong dispersion"),
)

ARCHGLASS_DESCRIPTION = (
    "Use for thin sheets of glass like window panes, where refraction does not matter "
    "(skips refraction during transmission, propagates alpha and shadow rays).\n\n"
    "Note that instead of using this option, you can also set the shadow color in the "
    "output node to white, which achieves the same effect while keeping the refraction "
    "for camera rays, which looks better if the edges of the glass sheets are visible"
)

THIN_FILM_DESCRIPTION = (
    "Simulate the effect of light waves interfering with themselves in a thin film "
    "coating on the surface of the material. The resulting colors are controlled by "
    "the film thickness, film IOR and the angle of incidence"
)

class LuxCoreSocketCauchyC(bpy.types.NodeSocket, LuxCoreSocketFloat):
    """
    For consistency of renewed variable naming, this class should be called 
    "LuxCoreSocketCauchyB". However, the name was retained for backward compatibility.
    """
    default_value: FloatProperty(name="Dispersion", default=0, min=0, soft_max=0.01342,
                                 step=0.1, precision=5, description=CAUCHYB_DESCRIPTION,
                                 update=utils_node.force_viewport_update)

    def draw(self, context, layout, node, text):
        # In smooth Glass Sellmeier mode the preset defines n(lambda), so the
        # manual Cauchy-B/Dispersion input is intentionally not shown.
        if (
            getattr(node, "bl_idname", "") == "LuxCoreNodeMatGlass"
            and not getattr(node, "architectural", False)
            and getattr(node, "dispersion_model", "CAUCHY") == "SELLMEIER"
        ):
            return

        if getattr(node, "architectural", False):
            # This socket is used on a glass node and is not exported because
            # archglass does not support dispersion
            layout.active = False

        super().draw(context, layout, node, text)


def _update_sellmeier_socket_visibility(node):
    """Hide complete IOR + Dispersion input sockets whenever Sellmeier is active.

    Applies to BOTH smooth Glass and RoughGlass. Architectural Glass stays out.
    """
    use_sellmeier = (
        not getattr(node, "architectural", False)
        and getattr(node, "dispersion_model", "CAUCHY") == "SELLMEIER"
    )

    for socket_name in ("IOR", "Dispersion"):
        try:
            node.inputs[socket_name].hide = use_sellmeier
        except (KeyError, AttributeError):
            pass


def _update_dispersion_model(self, context):
    _update_sellmeier_socket_visibility(self)
    utils_node.force_viewport_update(self, context)


def _update_rough(self, context):
    Roughness.toggle_roughness(self, context)
    _update_sellmeier_socket_visibility(self)


def _update_architectural(self, context):
    _update_sellmeier_socket_visibility(self)
    utils_node.force_viewport_update(self, context)


class LuxCoreNodeMatGlass(LuxCoreNodeMaterial, bpy.types.Node):
    """ Node for the three LuxCore materials glass, roughglass and archglass """
    bl_label = "Glass Material"
    bl_width_default = 190

    use_anisotropy: BoolProperty(name=Roughness.aniso_name,
                                  default=False,
                                  description=Roughness.aniso_desc,
                                  update=Roughness.update_anisotropy)
    rough: BoolProperty(name="Rough",
                         default=False,
                         description="Rough glass surface instead of a smooth one",
                         update=_update_rough)
    architectural: BoolProperty(update=_update_architectural, name="Architectural",
                                 default=False,
                                 description=ARCHGLASS_DESCRIPTION)
    use_thinfilmcoating: BoolProperty(name="Thin Film Coating", default=False,
                                      description=THIN_FILM_DESCRIPTION,
                                      update=ThinFilmCoating.toggle)
    ml_fine_roughglass: BoolProperty(
        name="ML Fine RoughGlass",
        default=False,
        description=(
            "Use ML Fine RoughGlass sampling for very small roughness values. "
            "Enables VNDF sampling and a smooth near-delta transition. "
            "Disable to use the original LuxCore RoughGlass roughness behaviour"
        ),
        update=utils_node.force_viewport_update
    )

    dispersion_model: EnumProperty(
        name="Dispersion Model",
        description="Choose the wavelength-to-IOR model",
        items=DISPERSION_MODEL_ITEMS,
        default="CAUCHY",
        update=_update_dispersion_model
    )

    sellmeier_preset: EnumProperty(
        name="Glass Preset",
        description="Optical glass used by the Sellmeier model",
        items=SELLMEIER_PRESET_ITEMS,
        default="N_BK7",
        update=utils_node.force_viewport_update
    )

    def init(self, context):
        self.add_input("LuxCoreSocketColor", "Transmission Color", (1, 1, 1))
        self.add_input("LuxCoreSocketColor", "Reflection Color", (1, 1, 1))
        self.add_input("LuxCoreSocketIOR", "IOR", 1.5)
        self.add_input("LuxCoreSocketCauchyC", "Dispersion", 0)
        ThinFilmCoating.init(self)
        
        Roughness.init(self, default=0.05, init_enabled=False)

        self.add_common_inputs()

        self.outputs.new("LuxCoreSocketMaterial", "Material")
        Roughness.update_anisotropy(self, context)
        _update_sellmeier_socket_visibility(self)
        

    def draw_buttons(self, context, layout):
        column = layout.row()
        column.enabled = not self.architectural
        column.prop(self, "rough")

        if self.rough:
            Roughness.draw(self, context, layout)
            layout.prop(self, "ml_fine_roughglass")

        # Rough glass cannot be archglass
        row = layout.row()
        row.enabled = not self.rough
        row.prop(self, "architectural")
        
        layout.prop(self, "use_thinfilmcoating")

        # Sellmeier is available for smooth Glass and RoughGlass.
        if not self.architectural:
            layout.separator()
            layout.prop(self, "dispersion_model")
            if self.dispersion_model == "SELLMEIER":
                layout.prop(self, "sellmeier_preset")

        if self.get_interior_volume():
            layout.label(text="Using IOR of interior volume", icon=icons.INFO)

    def sub_export(self, exporter, depsgraph, props, luxcore_name=None, output_socket=None):
        if self.rough:
            type = "roughglass"
        elif self.architectural:
            type = "archglass"
        else:
            type = "glass"

        definitions = {
            "type": type,
            "kt": self.inputs["Transmission Color"].export(exporter, depsgraph, props),
            "kr": self.inputs["Reflection Color"].export(exporter, depsgraph, props),
        }

        # Only use the glass node IOR socket if there is no interior volume
        if not self.get_interior_volume():
            definitions["interiorior"] = self.inputs["IOR"].export(exporter, depsgraph, props)

        cauchyb = self.inputs["Dispersion"].export(exporter, depsgraph, props)
        if self.inputs["Dispersion"].is_linked or cauchyb > 0:
            definitions["cauchyb"] = cauchyb

        # Runtime dispersion-model selection for Glass and RoughGlass.
        if not self.architectural:
            definitions["dispersionmodel"] = self.dispersion_model.lower()
            if self.dispersion_model == "SELLMEIER":
                definitions["sellmeierpreset"] = self.sellmeier_preset.lower()

        if self.use_thinfilmcoating:
            ThinFilmCoating.export(self, exporter, depsgraph, props, definitions)

        if self.rough:
            Roughness.export(self, exporter, depsgraph, props, definitions)
            definitions["fineroughglass.enable"] = self.ml_fine_roughglass
        self.export_common_inputs(exporter, depsgraph, props, definitions)

        return self.create_props(props, definitions, luxcore_name)


    def get_interior_volume(self):
        node_tree = self.id_data
        active_output = get_active_output(node_tree)
        if active_output:
            return utils_node.get_linked_node(active_output.inputs["Interior Volume"])
        return False
